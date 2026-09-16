# FROM postgres:12-alpine
FROM postgres:17.10-alpine

# Include extra setup scripts (eg datastore)
ADD --chmod=755 docker-entrypoint-initdb.d /docker-entrypoint-initdb.d
