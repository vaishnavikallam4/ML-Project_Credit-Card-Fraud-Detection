# Deployment and production hardening

This app is a fraud-workflow simulation. It does not connect to a bank, move real
money, or submit police reports. Carrier SMS remains simulated by default; an
optional MSG91 Flow integration can send messages when explicitly configured.
Do not deploy it for real customer data or regulated banking operations.

## Local demo

Copy `.env.example` to `.env`, install `requirements.txt`, and run
`python -m backend.app` from the project root. The development configuration
creates missing tables and seeds demo users when `DEMO_MODE=true`. Its default
SQLite database is `backend/instance/bank_fraud_simulation.db`; leave
`DATABASE_URL` unset to use that database, or set an absolute SQLite URL to
select a different local database.

## Production-mode safeguards

Set configuration through a deployment secret manager, not a committed `.env`:

- `FLASK_ENV=production`
- `SECRET_KEY` and `JWT_SECRET_KEY`: two independent random values, each at
  least 32 characters
- `DATABASE_URL`: persistent, managed non-SQLite database
- `REDIS_URL`: shared Redis/Valkey endpoint for rate limits (use `rediss://` for
  encrypted connections when supported by the provider)
- `TRUSTED_PROXY_COUNT`: number of trusted reverse proxies in front of the app
  (set to `1` for a single HTTPS proxy)
- `CORS_ORIGINS`: comma-separated exact HTTPS origins for the deployed frontend
- `DEMO_MODE=false`
- `AUTO_CREATE_DB=false`
- `PUBLIC_REGISTRATION_ENABLED=false`

The app refuses to start in production if these safety requirements are not met.
Production mode does not create tables or seed demo users automatically. Schema
changes use Flask-Migrate/Alembic. Review each generated migration, take a
database backup, and run `flask --app backend.app db upgrade` as an explicit
deployment step for a new, empty database. Existing databases created by earlier
versions must not run this initial migration blindly: compare their schema to
the revision first, and use `flask --app backend.app db stamp head` only after
confirming it already matches exactly. Otherwise, prepare a reviewed,
data-preserving forward migration. With a new, empty development database,
`flask --app backend.app init-db` remains available for the local demo; it is
not the production migration process. With a prepared schema, provision a user
interactively using
`flask --app backend.app create-user --name "Bank Admin" --email admin@example.com --role BANK_ADMIN`.
The command prompts for the password without putting it in shell history; it
requires at least 12 characters. Provision customer accounts through the same
command with `--role CUSTOMER`.

Serve the app with a production WSGI server behind HTTPS; never expose Flask's
development server. For example, after installing `requirements.txt`, run
`waitress-serve --listen=127.0.0.1:8080 backend.app:app` behind a reverse proxy
that terminates HTTPS and replaces forwarded headers. Set
`TRUSTED_PROXY_COUNT` to the exact number of trusted proxies, and block public
access to the Waitress port; only then should the app trust forwarded headers
for client-IP rate limits and HTTPS security headers. The PostgreSQL driver is
included in `requirements.txt`. Keep database backups,
access monitoring, and secret rotation in the deployment environment. The
`/api/health` endpoint verifies the database is reachable and that its base
schema exists. Login is limited to five attempts per minute and twenty per hour
per client IP; registration is limited to three requests per hour. Production
requires Redis-backed shared rate-limit storage across worker processes.

To enable the optional MSG91 SMS integration, set `SMS_MODE=msg91` and provide
`MSG91_AUTH_KEY` and `MSG91_TEMPLATE_ID` through the deployment secret manager.
Configure the approved MSG91 Flow template to accept the notification text as
`VAR1`, and set `SMS_DEFAULT_COUNTRY_CODE` for local-format phone numbers.
Without those settings, SMS stays in simulation mode. `ACCEPTED` means MSG91
accepted the request; it does not confirm delivery to the handset. Provider
credentials are never returned by the application.

## Still required before any real banking use

Production-mode safeguards alone do not make this app suitable for real banking.
Real deployment still requires a bank-approved provider and sandbox integration,
security assessment, authorization and audit controls, identity verification,
account lockout and MFA flows, privacy/compliance review, tested migration and
recovery plans, and independent end-to-end testing. Keep bank, SMS, and police
actions in simulation mode until those workstreams are formally approved and
implemented.
