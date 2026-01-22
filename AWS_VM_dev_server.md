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
docker compose -f docker-compose.dev.yml up -d --build ckan
```

# Open the AWS Ubuntu VM in VS Code (Remote – SSH)

### 1) Install the extension

In VS Code: **Extensions → “Remote - SSH”** (by Microsoft) → Install.

### 2) Add an SSH host entry

Open **Command Palette** → `Remote-SSH: Open SSH Configuration File…`
Choose your config (Windows usually: `C:\Users\<you>\.ssh\config`) and add:

```sshconfig
Host ckan-dev
  HostName instrument-test.data.auscope.org.au
  User ubuntu
  IdentityFile C:\Users\<you>\.ssh\ckan-dev
  IdentitiesOnly yes
```

> Replace the `IdentityFile` path with your actual key file.

### 3) Connect

Command Palette → `Remote-SSH: Connect to Host…` → select **ckan-dev**

When prompted for the remote OS, select **Linux** (Ubuntu).

You should see `SSH: ckan-dev` in the bottom-left once connected.

### 4) Open a folder on the VM

In the **Remote** VS Code window:

* **File → Open Folder…**
* Enter the remote path (example):

  * `/opt/ckan` (or wherever your repo is)
* Click **OK**

Now you can browse/edit files on the VM directly.

### 5) If it prompts for OS again later

Always pick **Linux** for Ubuntu. Picking Windows can cause errors like `powershell: command not found`.

### Quick troubleshooting

* **Timeout:** SSH port 22 not reachable (security group / IP).
* **Permission denied:** wrong key or wrong user (Ubuntu AMI user is usually `ubuntu`).


## Test Change