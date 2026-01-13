# Quick Guide

**To connect:**
You need the private key: `ckan-dev`

_in pwsh:_

```
ssh -i $env:USERPROFILE\.ssh\ckan-dev ubuntu@instrument-test.data.auscope.org.au
```

_in bash:_

```
ssh -i ~/.ssh/ckan-dev ubuntu@instrument-test.data.auscope.org.au
```

# CKAN Development Server - Next Steps

## 1. SSH into the server

Use VS Code Remote-SSH or terminal:

```bash
ssh ubuntu@instrument-test.data.auscope.org.au
```

## 2. Clone CKAN repository

```bash
cd /opt/ckan
git clone https://github.com/ckan/ckan.git
cd ckan
```

Or clone your custom CKAN repository:

```bash
cd /opt/ckan
git clone https://github.com/AuScope/AuScope-instrument-registry.git .
```

## 3. Create docker-compose.yml

Create or use existing docker-compose.yml. Example structure:

```yaml
version: "3"

services:
  postgres:
    image: postgres:14
    environment:
      POSTGRES_USER: ckan
      POSTGRES_PASSWORD: ckan
      POSTGRES_DB: ckan
    volumes:
      - /opt/ckan/postgres-data:/var/lib/postgresql/data
    networks:
      - ckan-network

  solr:
    image: ckan/ckan-solr:2.10-solr9
    volumes:
      - /opt/ckan/solr-data:/var/solr
    networks:
      - ckan-network

  redis:
    image: redis:7
    volumes:
      - /opt/ckan/redis-data:/data
    networks:
      - ckan-network

  ckan:
    build: .
    ports:
      - "5000:5000"
    environment:
      CKAN_SQLALCHEMY_URL: postgresql://ckan:ckan@postgres/ckan
      CKAN_SOLR_URL: http://solr:8983/solr/ckan
      CKAN_REDIS_URL: redis://redis:6379/0
      CKAN_SITE_URL: https://instrument-test.data.auscope.org.au
    volumes:
      - /opt/ckan/data:/var/lib/ckan
      - ./:/usr/lib/ckan/default/src/ckan # Mount source for development
    depends_on:
      - postgres
      - solr
      - redis
    networks:
      - ckan-network

networks:
  ckan-network:
    driver: bridge
```

## 4. Start CKAN

```bash
cd /opt/ckan
docker compose -f docker-compose.dev.yml up -d
```

## 5. Check logs

```bash
docker compose logs -f ckan
```

## 6. Setup SSL with Let's Encrypt

Once CKAN is running on port 5000:

```bash
sudo certbot --nginx -d instrument-test.data.auscope.org.au
```

Follow the prompts. Certbot will:

- Obtain SSL certificate
- Configure Nginx to use HTTPS
- Setup automatic renewal

## 7. Verify HTTPS

Access: https://instrument-test.data.auscope.org.au

## 8. Initialize CKAN database

```bash
docker compose exec ckan ckan -c /etc/ckan/production.ini db init
```

## 9. Create admin user

```bash
docker compose exec ckan ckan -c /etc/ckan/production.ini sysadmin add admin
```

## 10. VS Code Remote-SSH Setup

1. Install "Remote - SSH" extension in VS Code
2. Add SSH config (~/.ssh/config):
   ```
   Host ckan-dev
     HostName instrument-test.data.auscope.org.au
     User ubuntu
     IdentityFile ~/.ssh/id_rsa
   ```
3. Connect via Remote-SSH
4. Open /opt/ckan folder
5. Edit code directly on the server

## Data Persistence

All data is persisted in:

- PostgreSQL: /opt/ckan/postgres-data
- Solr: /opt/ckan/solr-data
- Redis: /opt/ckan/redis-data
- CKAN uploads: /opt/ckan/data

These directories are outside the container and will persist across container restarts.

## Useful Commands

```bash
# View all containers
docker ps

# Stop all services
docker compose down

# Restart a service
docker compose restart ckan

# View logs
docker compose logs -f

# Execute command in container
docker compose exec ckan bash

# Rebuild CKAN container after code changes
docker compose up -d --build ckan
```
