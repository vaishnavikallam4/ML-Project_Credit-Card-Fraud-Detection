# Velora Bank Fraud Intelligence

## Project documentation — implemented scope

**Document status:** Describes the project as implemented in this workspace on
October 6, 2026. It is a software project and demonstration guide, not a bank
operating manual, compliance certification, or approval for handling real
financial data.

## 1. Executive summary

Velora Bank Fraud Intelligence is a browser-based banking and fraud-workflow
simulation built with Flask, SQLAlchemy, SQLite for local development, and a
vanilla JavaScript frontend. It demonstrates two application roles:

- **Customer:** views their own simulated accounts, cards, transactions, fraud
  alerts, verification prompts, notifications, investigation cases, and messages
  with the bank.
- **Bank admin:** reviews operational metrics, searches a customer-name
  directory, opens an individual customer profile, controls that customer's
  cards, replies to customer messages, and records case-investigation outcomes.

A synthetic machine-learning score and behavior/rule score are combined to
classify simulated transactions. Suspicious transactions are held as pending
for customer review. Reporting a transaction creates a bank-visible fraud case
and temporarily holds the linked card.

**Nothing in this application connects to a real bank, moves real money, or
files a real police report.** Balances, transactions, and police-report
references are simulated. Carrier SMS is simulated by default; an optional
MSG91 Flow integration sends phone alerts only after its approved template and
credentials are configured.

## 2. Implemented scope and boundaries

| Area | Implemented behavior | Important boundary |
|---|---|---|
| Login and roles | Customer and `BANK_ADMIN` sign-in using email or phone and a password; JWT-protected API requests | No identity-proofing, MFA, password-reset, or enterprise identity provider |
| Customer registration | Creates customer-role users when public registration is enabled | Production defaults disable registration; do not use demo signup for bank onboarding |
| Customer accounts | Displays customer-owned accounts; customer can create a simulated account | Not connected to a core-banking system; account details and balances are demo data |
| Cards | Displays simulated cards, linked account, status, and last four digits; customer can create a simulated card | Not a payment card; no card network, authorization processor, PAN, or CVV handling |
| Transactions | Simulates debit/credit, fraud scoring, account-ledger changes, and status | Does not initiate or settle payments |
| Fraud review | Customer can confirm a pending flagged transaction or report a transaction from its notification | Model output is a screening signal, not a definitive fraud determination |
| Customer notifications | In-app transaction/fraud messages and a phone-message log; optional MSG91 SMS | SMS is simulated unless MSG91 is configured; provider acceptance is not a delivery receipt |
| Customer/admin messaging | Customer can request card action and discuss a fraud case; admin can reply from the named customer's profile | Requests are reviewed by admin; messages and card controls are simulator records |
| Admin customer directory | Name-only customer rows with a separate profile action | Contact and financial details are intentionally shown only in the selected profile |
| Admin profile | Shows only the selected customer's details, accounts, cards, transactions, alerts, notifications, phone log, and cases | This is a simulation UI and is not a substitute for bank case-management controls |
| Card controls | Admin can place a card on hold, block it, or restore it via the profile | Changes only the simulator's database state |
| Investigation | Admin can add notes, resolve a case as fraud or false alarm, and record a police-report reference | Report recording is simulated; no submission or acknowledgment from police occurs |
| Production safeguards | Validates production config, pins CORS, adds web security headers, disables demo seeding/schema auto-create/signup by default, and provides WSGI deployment guidance | These safeguards alone do not make this system suitable for production banking |

## 3. Roles and user journeys

### 3.1 Customer

1. Sign in using email or phone and password.
2. View only their own accounts, cards, transactions, notifications, and fraud
   alerts. The server scopes customer data to the authenticated user ID.
3. Create a simulated account or card from the customer dashboard.
4. Submit a simulated debit or credit using an active card, amount, merchant,
   and location.
5. See a transaction notification labelled with the automated `LOW`, `MEDIUM`,
   or `HIGH` risk level and an explanation that the score is only a screening
   signal. Reviewable transactions offer **Yes, it was me** and
   **No, report fraud** in the alert panel; authorized transactions also offer
   those review actions in transaction history.
6. Confirming a pending transaction authorizes it and applies the simulated
   ledger change. Reporting a transaction creates a case and puts its card on
   `HOLD`; the customer can see the case/notification in their dashboard.
7. Use **Talk to the bank** to link a message to a case, request a temporary
   hold or block, and ask for transaction details. The bank admin can see the
   message under the customer's name and reply from the customer profile.

The separate fraud-alert panel also presents the confirmation/report actions
for open model-flagged alerts. Notifications show phone messages as simulated
and explicitly disclose that no carrier message was sent.

**Ledger behavior:** Low-risk transactions are authorized and applied to the
simulated balance immediately. A customer can still report one as unauthorized
later; the app records the case and places the card on hold, but does not
automatically reverse that already-applied balance movement. A pending
medium/high-risk debit is not applied to the balance until the customer
confirms it. If an admin later resolves a pending case as a false alarm, the
pending transaction is authorized and applied then.

### 3.2 Bank admin

1. Sign in with a separately provisioned `BANK_ADMIN` account.
2. Review top-level customer, account, card, risk-event, and case metrics, plus
   operations analytics and aggregate transaction-risk counts.
3. Search the customer directory. Each row shows the customer's name and an
   **Open profile** action; it does not expose financial/contact details on the
   directory landing page.
4. Open one profile to review that customer's contact details, accounts,
   balances, cards/status controls, transaction history, phone-alert log,
   notifications, alerts, and fraud cases.
5. For a customer-reported case, add investigation notes and resolve it:
   - **Fraud:** marks the transaction fraudulent and the card `BLOCKED`.
   - **False alarm:** authorizes a pending transaction if needed and restores a
     `HOLD` card to `ACTIVE`.
6. For a fraud-confirmed case, record a simulated police station and reference.
   The generated reference is a local record, not a police filing.
7. Read and reply to the customer's messages in the selected customer profile.
The admin landing page does not show the customer transaction/notification
workspace. Administrators must open a particular customer profile to view that
person's information. Admin card controls change only that card.

## 4. Transaction and risk workflow

### 4.1 Request validation and account simulation

The transaction API requires an authenticated customer, an owned active card,
a linked customer account, a finite amount greater than zero, and sufficient
balance for a debit. A credit is incoming; a debit is outgoing. The ledger
updates only simulated account balances.

Each request builds a model feature row containing amount, hour, weekend flag,
merchant category, transaction type, country/international indicator, estimated
customer average, recent transaction count, and device risk. Some values (for
example country/category/device/recent count) are currently simplified
simulation inputs rather than verified external signals.

### 4.2 Risk calculation

The checked-in training pipeline creates a **synthetic 2,000-row dataset** from
hand-coded patterns and trains a Random Forest classifier. Scikit-learn
preprocessing includes numeric imputation/scaling and one-hot categorical
encoding; SMOTE is applied to the training split. The serialized model and
preprocessor are in `backend/model/`.

The transaction endpoint combines:

- ML fraud probability, returned as a value from 0 to 1;
- behavioral risk based on up to 50 earlier transactions (amount deviations,
  large amounts, late-night timing, and short-window transaction frequency);
- an additional amount factor: 8 at 8,000+, 15 at 20,000+, 25 at 50,000+, and
  35 at 100,000+.

The overall score is the larger of the ML probability converted to a 0–100
score or the behavior score, plus the amount factor, capped at 100:

| Overall score | Risk level | Initial transaction status |
|---:|---|---|
| Below 45 | `LOW` | `AUTHORIZED` |
| 45–74.99 | `MEDIUM` | `PENDING` |
| 75–100 | `HIGH` | `PENDING` |

Only pending medium/high transactions automatically create an open
`FraudAlert`. The model's own probability/prediction are stored separately from
the combined risk level. The model uses synthetic data and simplified features;
its classification metrics or probability must not be treated as real-world
fraud performance.

## 5. Case and notification state behavior

- New transactions create one in-app notification and one SMS-channel record.
  SMS is sent through MSG91 only when enabled and configured; otherwise it is
  explicitly marked as simulated.
- A pending flagged alert may be confirmed (`YES`) or reported (`NO`).
- A transaction notification provides the same review actions for ordinary
  authorized transactions. Reporting one records a case and holds the card.
- Pending unrecognized transactions become `FRAUD_REPORTED`; already-authorized
  transactions remain `AUTHORIZED` while the bank reviews the report.
- Customer reports are written to audit records and create an open fraud case.
- Admin fraud resolution sets the transaction to `FRAUDULENT` and card to
  `BLOCKED`.
- Admin false-alarm resolution sets the transaction to `AUTHORIZED` and restores
  a held card, if applicable.
- Case decisions create a customer in-app notification and an SMS-channel
  record, delivered only when MSG91 is configured.
- A police-report record can only be created after a case is resolved as fraud.
  The report status/reference is local simulation state.

## 6. Data model

The SQLAlchemy models are registered in `backend/models/`.

| Model/table | Purpose |
|---|---|
| `User` / `users` | Customer/admin identity, email, optional phone, role, password hash, and address |
| `Account` / `accounts` | Customer-owned simulated account, account number/type, status, and balance |
| `Card` / `cards` | Simulated card linked to a customer/account with type, expiry fields, last four, and status |
| `Transaction` / `transactions` | Simulated merchant activity, amount, direction/type, state, risk/prediction fields, and time |
| `FraudAlert` / `fraud_alerts` | Customer/transaction-linked risk alert, status, and resolution time |
| `FraudCase` / `fraud_cases` | Customer report, linked card/transaction, case state, customer response, and resolution |
| `InvestigationNote` / `investigation_notes` | Admin-authored case notes |
| `Notification` / `notifications` | In-app or SMS message, optional transaction/case links, and delivery status |
| `PoliceReport` / `police_reports` | Simulated police follow-up reference, station, status, summary, and filing admin |
| `AuditLog` / `audit_logs` | Recorded customer/admin actions against application entities |

Passwords are hashed with Passlib PBKDF2-SHA256. The app does not store full
payment-card numbers or CVVs; card creation accepts and stores only the
displayed last four digits plus simulated card metadata.

## 7. Main API surface

Except where noted, endpoints below require a bearer JWT. Customer records are
scoped to the signed-in customer; admin-only operations enforce the admin role.

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/` | Public | Serve the browser application |
| `GET` | `/api/health` | Public | Check that the database and base user table are reachable |
| `POST` | `/api/auth/register` | Public, configurable | Register a customer if public signup is enabled |
| `POST` | `/api/auth/login` | Public | Authenticate by email or phone and receive a JWT |
| `GET` | `/api/auth/me` | Signed in | Get the current user's profile |
| `GET`, `POST` | `/api/accounts` | Customer/admin read; customer create | Read accessible accounts or create a customer's simulated account |
| `GET`, `POST` | `/api/cards` | Customer/admin read; customer create | Read accessible cards or create a simulated linked card |
| `GET`, `POST` | `/api/transactions` | Customer own data; admin bank-wide read; customer create | Read transaction history or score/process a simulated transaction |
| `GET` | `/api/alerts` | Customer own alerts; admin bank-wide alerts | Read fraud alerts |
| `POST` | `/api/alerts/<alert_id>/respond` | Owning customer | Confirm or report an open model-generated alert |
| `POST` | `/api/alerts/transactions/<transaction_id>/respond` | Owning customer | Confirm or report a transaction from the notification center |
| `GET` | `/api/notifications` | Customer only | Read that customer's notifications; admins use selected-profile API |
| `GET` | `/api/cases` | Customer/admin | Read the customer's own cases or the bank investigation queue |
| `GET` | `/api/cases/<case_id>` | Admin only | Read a case and its transaction summary |
| `POST` | `/api/cases/<case_id>/note` | Admin only | Add an investigation note |
| `POST` | `/api/cases/<case_id>/resolve` | Admin only | Resolve as `FRAUD` or `FALSE_ALARM` |
| `POST` | `/api/cases/<case_id>/police-report` | Admin only | Record simulated police follow-up after fraud confirmation |
| `GET` | `/api/admin/users` | Admin only | Fetch minimal customer directory fields |
| `GET` | `/api/admin/users/<user_id>` | Admin only | Fetch the selected customer's full profile and activity |
| `PATCH` | `/api/admin/cards/<card_id>/status` | Admin only | Set a simulated card to `ACTIVE`, `HOLD`, or `BLOCKED` |
| `GET`, `POST` | `/api/messages` | Customer only | Read or send messages in the signed-in customer's conversation |
| `GET`, `POST` | `/api/messages/customers/<customer_id>` | Admin only | Read or reply to the selected customer's conversation |

## 8. Project structure

```text
bank_fraud_simulation/
|-- backend/
|   |-- app.py                 Flask application factory and CLI commands
|   |-- config.py              Development/production configuration checks
|   |-- extensions.py          SQLAlchemy, JWT, and CORS extensions
|   |-- models/                SQLAlchemy entities and relationships
|   |-- routes/                Auth, account, card, transaction, alert, case, admin APIs
|   |-- services/              Model scoring, behavior, ledger, and demo seed
|   |-- model/                 Serialized model, preprocessor, training metrics
|   |-- static/                Frontend CSS and JavaScript
|   `-- templates/index.html   Single-page application shell
|-- dataset/                   Project dataset area
|-- frontend/                  Additional frontend/project area
|-- model/                     Additional model/project area
|-- migrations/                Alembic environment and initial schema revision
|-- backend/tests/             Focused production-safeguard regression tests
|-- .env.example               Local configuration template
|-- .gitignore                 Local secrets, instance DB, caches, venv exclusions
|-- requirements.txt           Python dependencies, including WSGI/migrations/rate limits
|-- DEPLOYMENT.md              Deployment safeguards and deployment prerequisites
`-- SYSTEM_DOCUMENTATION.md    This document
```

## 9. Local development

Run commands from the project root:

```powershell
Copy-Item .env.example .env
python -m pip install -r requirements.txt
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
python -m backend.app
```

Open `http://127.0.0.1:5000/`. The local development configuration creates
missing tables. When `DEMO_MODE=true`, the demo seed adds initial sample users
and a simulated account/card. By default, the app uses
`backend/instance/bank_fraud_simulation.db`; leave `DATABASE_URL` blank to keep
using that database.

Demo sign-in:

| Role | Email | Password |
|---|---|---|
| Bank admin | `admin@demo.bank` | `Demo@123` |
| Customer | `customer@demo.bank` | `Demo@123` |

These shared sample credentials are for local demonstration only. Do not reuse
them outside the isolated simulator.

## 10. Production-mode safeguards and explicit setup

Production startup expects values supplied by a deployment secret manager:

- `FLASK_ENV=production`
- independent random `SECRET_KEY` and `JWT_SECRET_KEY`, at least 32 characters
- persistent managed non-SQLite `DATABASE_URL`
- shared Redis/Valkey `REDIS_URL` for production request-rate limits
- `CORS_ORIGINS` containing only exact HTTPS frontend origins
- `TRUSTED_PROXY_COUNT` set to the exact number of trusted HTTPS reverse proxies
- `DEMO_MODE=false`
- `AUTO_CREATE_DB=false`
- `PUBLIC_REGISTRATION_ENABLED=false`

The production configuration rejects missing/weak keys, demo mode, SQLite,
wildcard or non-HTTPS CORS, automatic schema creation, public registration, and
non-shared production rate-limit storage.
The local Flask development server is not allowed when launched in production
mode. Use a production WSGI server behind HTTPS. See [DEPLOYMENT.md](./DEPLOYMENT.md)
for Waitress example commands, database setup notes, and remaining deployment
requirements.

Available application CLI commands:

- `flask --app backend.app db upgrade` applies checked-in Alembic schema
  migrations. Review the migration and back up the target database before use.
- `flask --app backend.app init-db` creates missing tables explicitly. It is
  for a new empty database; it is not a migration system and must not be used
  to evolve a live schema.
- `flask --app backend.app create-user --name "Bank Admin" --email admin@example.com --role BANK_ADMIN`
  interactively provisions a customer/admin and prompts for a password without
  echoing it. Passwords supplied to this command must have at least 12
  characters.

## 11. Security and operational controls implemented

- JWT-protected application APIs and role checks for customer/admin operations.
- Customer-scoped queries for customer accounts, cards, transactions, alerts,
  and notifications.
- Server-side ownership checks for account/card/transaction actions.
- Passlib PBKDF2-SHA256 password hashing.
- One-hour JWT access tokens.
- Login limit of five attempts per minute and twenty per hour per client IP;
  public registration limit of three attempts per hour. Production limits use
  shared Redis storage across application workers.
- Configurable trusted-proxy handling for correct client-IP and HTTPS
  detection behind a locked-down reverse proxy.
- Initial Alembic schema revision and Flask-Migrate CLI.
- Production configuration guardrails, exact-origin CORS configuration, and
  disabled-by-default production registration/demo seed/schema auto-creation.
- Browser security response headers, including content-type/frame/referrer
  policies, a Content Security Policy, and HTTPS HSTS responses.
- Request body size limit of 1 MiB.
- A database-aware `/api/health` readiness check.
- `.gitignore` excludes `.env`, virtual environments, Python caches, and local
  instance database files.

These are baseline project safeguards, not a formal security assessment.

## 12. Known limitations and pending work

1. **No real financial rails:** bank identity, accounts, balances, authorizations,
   settlements, reversals, and card controls are not connected to any bank or
   processor.
2. **Messaging is optional; police is simulated:** MSG91 SMS requires approved
   provider configuration and real delivery receipts are not tracked. Police
   report actions create local simulation records only.
3. **Synthetic model data:** the training set is generated from hand-coded
   patterns. It does not establish production accuracy, calibration, or
   fairness; signals such as device risk are currently simplified.
4. **Schema evolution:** an initial Alembic migration is included; each future
   migration still needs review, backup, and a tested rollback plan before
   deployment.
5. **Login abuse controls:** request rate limits are implemented, but account
   lockout policy, MFA, password reset/recovery, and identity verification are
   not implemented.
6. **Web-session hardening:** the browser keeps the JWT in `localStorage`.
   Production use requires a threat-modelled session/token-storage design and
   additional browser protections.
7. **Compliance and operations:** no bank approval, privacy/legal review,
   regulatory controls, independent penetration test, disaster-recovery plan,
   managed production infrastructure, monitoring/alerting, or real-data approval
   is included.
8. **Test coverage:** a focused `unittest` suite covers production guardrails,
   rate limits, registration disablement, database migrations, demo-seed
   behavior, and security headers. It is not a comprehensive end-to-end or
   security regression suite.
9. **Local database:** the included SQLite database and sample users are demo
   state. Keep it out of version control and never copy it into a production
   environment.

**Conclusion:** the project implements an end-to-end educational simulation of
customer transaction review and bank fraud-case operations. It is not a real
banking product and must not be used to process real money or regulated
customer data.
