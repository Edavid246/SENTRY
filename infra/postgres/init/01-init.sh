#!/usr/bin/env bash
# First-run database initialisation for defence-gateway (runs only on an empty
# data directory). Sourced by the postgres docker entrypoint, so no `set -u`
# (it would alter the entrypoint's shell) — fail loudly instead.
#
# Roles:
#   gateway_owner — owns schema objects; runs migrations; not a superuser.
#   gateway_app   — runtime role for the API; NOSUPERUSER, NOBYPASSRLS so
#                   PostgreSQL row-level security always applies to it.
#
# Passwords come from the container environment (compose placeholders in
# .env.example), never from this committed file.

if [ -z "${GATEWAY_OWNER_PASSWORD:-}" ] || [ -z "${GATEWAY_APP_PASSWORD:-}" ]; then
  echo "FATAL: GATEWAY_OWNER_PASSWORD and GATEWAY_APP_PASSWORD must be set" >&2
  false
fi

psql -v ON_ERROR_STOP=1 \
  -v owner_password="$GATEWAY_OWNER_PASSWORD" \
  -v app_password="$GATEWAY_APP_PASSWORD" \
  --username "${POSTGRES_USER:-postgres}" \
  --dbname "${POSTGRES_DB:-gateway}" <<'SQL'
CREATE ROLE gateway_owner LOGIN PASSWORD :'owner_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE gateway_app LOGIN PASSWORD :'app_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

ALTER DATABASE gateway OWNER TO gateway_owner;
CREATE DATABASE gateway_test OWNER gateway_owner;

GRANT CONNECT ON DATABASE gateway TO gateway_owner, gateway_app;
GRANT CONNECT ON DATABASE gateway_test TO gateway_owner, gateway_app;

\connect gateway
CREATE EXTENSION IF NOT EXISTS vector;
GRANT USAGE ON SCHEMA public TO gateway_owner, gateway_app;

\connect gateway_test
CREATE EXTENSION IF NOT EXISTS vector;
GRANT USAGE ON SCHEMA public TO gateway_owner, gateway_app;
SQL
