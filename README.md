# Maziwa Cloud: dairy management as a SaaS (Django + React)

```
maziwa-cloud/
  backend/    Django REST API (multi-tenant), this README, Dockerfile, docker-compose.yml
  frontend/   React (Vite) app
```

## Run it
```bash
# backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py makemigrations && python manage.py migrate
python manage.py createsuperuser        # YOU, the platform operator
python manage.py runserver

# frontend (second terminal)
cd frontend && npm install && npm run dev      # http://localhost:5173
```
Postgres: set `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` (or use docker-compose).
If you are upgrading an older copy of this project, delete the old database and migrations first:
the user model changed (one login can now belong to several dairies).

## Code structure (one Django app per business area)

```
backend/
  config/              settings, root urls (includes every app's urls.py under /api/)
  core/                shared kernel, no business rules: utils (phone, encryption), tenancy (TenantMixin),
                       pagination, documents (CSV/PDF helpers), backup_db command
  apps/
    tenants/           Organization (the dairy), Plan, Invoice; plan limits; subscription billing
    accounts/          Role, Membership, permissions, login/password/security, team (members + roles)
    collection/        CollectionCentre, Route, Transporter, RouteTrip (route sheet), TransporterPayment
    farmers/           Farmer (on a Route); farmer registration
    milk/              MilkRate, MilkCollection (quality, rejection), QualityTier (fat/protein bonuses)
    store/             FeedMill, Product (+ price history), CreditOrder, StockMovement, PurchaseOrder,
                       StockTake, CashSale (point of sale)
    advances/          Advance (cash advances and loans), AdvanceSettings
    herd/              Animal, HealthEvent (vaccination, AI, calving, treatment), AnimalMilkRecord
    sales/             Buyer, MilkSale (milk sold to processors)
    payments/          farmer Payment (+ deductions incl. advances), credit repayments, payment slips
    payroll/           PayrollEntry, payslips
    expenses/          Expense
    notifications/     in-app Notification, SmsLog, Africa's Talking sender
    mpesa/             MpesaConfig, MpesaTransaction, Daraja client, STK/B2C flows and callbacks
    audit/             AuditLog, signals, request middleware, token authentication
    reports/           management reports, statements, CSV/PDF exports } composition layer:
    platform_admin/    operator screens (no models)          } reads many apps,
    dashboard/         /me/ session + home summary           } nothing depends on it
```
Each app has `models.py`, `serializers.py`, `views.py`, `urls.py`, and `services.py` where there is business logic
(views stay thin; rules live in services). Dependencies only point downward:
`tenants` < `accounts` < `collection` < `farmers` < `milk` / `store` / `advances` / `herd` / `sales` < `payments` / `payroll` <
`expenses` / `notifications` < `mpesa` < composition layer. There are no import cycles (checked), and models reference other apps only through
foreign keys or reverse relations. To add a feature, create `apps/<name>/` with its own `apps.py`, register it in
`INSTALLED_APPS` and `config/urls.py`.

## Business modules

### Milk quality and bonuses (`milk`)
Each delivery records fat %, protein %, an **alcohol test** and **rejected litres** with a reason. A failed alcohol test
rejects the whole delivery. Rejected litres are never paid and the farmer is told by alert/SMS. Under *Milk price*
the dairy sets **quality tiers**: when fat or protein reaches a level, X shillings per litre are added (or taken off
with a negative number). The highest tier reached counts. Payments are `accepted litres x (base price + bonus)`.

### Printable statements
*Exports* > *Farmer statement* gives one PDF per farmer for any period: milk delivered and rejected, quality bonus,
feed taken on credit, repayments, advances, deductions and net pay. Farmers can print their own. A one-page slip
is also on every payment and payslip.

### Cash advances and loans (`advances`)
A farmer requests an advance; staff with *advances.manage* approve or decline, then pay by M-Pesa (B2C) or cash.
Rules per dairy: maximum outstanding per farmer and an optional one-off fee. Advances are recovered automatically
from milk payments, **after feed credit**, oldest first, never below zero; leftovers carry forward.

### Herd health and per-cow production (`herd`)
Animals per farmer; vaccinations, treatments, deworming, AI/service, pregnancy checks and calving with cost, vet,
**milk withdrawal days** and next-due dates. Expected calving is worked out from the last AI (283 days). The milk
screen warns when a farmer has animals under withdrawal. Record milk per cow and see the best and worst cows.
Vet costs post to *Expenses* only when staff tick "the dairy paid the vet" (farmers' own costs never reach the
dairy's books). Run `python manage.py send_herd_reminders` daily (cron) to alert farmers 3 days before something is due.

### Milk sales and income (`sales`)
Buyers (Brookside, New KCC...), milk sold with litres and price, money received in parts, and what buyers still owe.

### Inventory depth (`store`)
Every stock change is logged (stock ledger). **Purchase orders** to feed mills: receiving one adds stock and records
a Feed purchase expense. **Stock take**: count the shelf, differences post as adjustments with their value.
**Low-stock alerts** from each product's reorder level (dashboard and store screen). **Cash sales** (cash or
M-Pesa) with a PDF receipt, next to credit orders. Stock can no longer be edited directly, only through these.

### Collection routes and centres (`collection`)
- **Centres**: where milk is bulked and cooled (location, cooling tank, capacity). **Routes**: a pick-up round with its
  farmers (assign farmers on the Farmers screen), the centre it delivers to and its usual transporter.
- **Route sheets**: one per route per milking. *Open sheets for all routes* creates them for the day. **Print** a sheet for
  the transporter (farmers on the route, blank columns for litres, fat, alcohol test and signature), then **Record** what was
  written: litres, fat, protein, rejected litres and a failed alcohol test per farmer. Farmers get their usual alerts.
  When the milk reaches the centre, **Receive** it with the measured litres and temperature. The sheet then locks and shows
  the **difference** between litres collected and litres received (negative = lost or spilled on the way).
- **Per-route totals**: every delivery remembers its route and centre. Reports: *Daily litres by route*, *Route sheets*,
  *Centres* and *Transporters* (table, chart, CSV, PDF).
- **Transporters** are paid per litre carried. *Transporters* shows litres and the amount due for any period; *Record payment*
  posts a **Transport** expense and blocks paying the same period twice.
- A transporter can log in as a normal member: give a custom role `milk.record` + `routes.view` so they can fill in sheets
  but not manage anything. New permissions: `routes.view`, `routes.manage` (Milk Clerk gets both, Accountant gets view).
- Existing farmers' free-text route is replaced by a real route link, so recreate the database (see below).

### Reports (`reports`)
Daily litres by route, route sheets, centres, transporters, top and bottom suppliers, credit exposure by farmer (feed credit plus advances against
the last 30 days of milk), monthly profit and loss and a 6-month trend; each as a table, chart, CSV and PDF.
Profit and loss counts income = milk sales + feed sold on credit + cash sales, and costs = milk paid to farmers
(including bonus) + all expenses (salaries, vet, purchase orders...). It also shows litres collected vs sold (loss %),
farmer payout as % of milk sales, price paid vs price sold per litre, and what buyers and farmers are owed.
It does not track the purchase cost of feed that is sold (feed purchases are expensed when received).

### New permissions (tick them under *Team and roles*)
`advances.view/request/manage`, `herd.view/manage`, `sales.view/manage`, `pos.sell`, `reports.view`.
Defaults: farmers get advances (view, request) and herd (view, manage); Accountant gets advances, sales and reports;
Store Keeper gets `pos.sell`; Milk Clerk gets `herd.view`; Manager gets everything except team, billing and M-Pesa.

## Dairies (tenants), users and membership
- A **dairy** is a tenant. All data belongs to one dairy and every query is limited to it.
- A **user** is one login (username + password). A user can be a **member of many dairies**, with a
  different role in each (owner of one, milk clerk in another, farmer in a third).
  The app sends the chosen dairy in the `X-Dairy` header; the header dropdown switches dairy.
- Signing up with an existing username and its password starts a second dairy under the same login.
  A farmer registering with a phone that already has an account joins the new dairy with that same login.
- Each dairy owner has their own members; owners never see other dairies' data.

## Roles and permissions
- Every dairy gets default roles: **Owner** (everything, locked), **Manager**, **Milk Clerk**, **Store Keeper**,
  **Accountant** and **Farmer** (locked, sees only their own records).
- Under *Team and roles* the owner (or anyone given `team.manage`) adds members, creates new roles, ticks the
  permissions each role has, and assigns roles. Custom roles can be edited or deleted (not while in use).
- Permissions: view/manage farmers, view/record milk, set milk price, view/manage store, sell on credit,
  view/manage farmer payments, view/manage expenses, view/run payroll, manage team, manage billing.
- The server checks the permission on every request; the menu only hides what you cannot use.
- **Platform admin** (the Django superuser, log in normally) sees all dairies, invoices and **every role in every dairy**.

## Expenses
Record costs by category (feed purchase, transport, fuel, repairs, utilities, vet, cooling, salaries, other),
filter by date/category and see totals per category. Salary expenses are created automatically by payroll.

## Payroll (paying people who work for the dairy)
- Set each staff member's monthly salary and phone under Team.
- *Payroll* > pick a month > create payslips for everyone with a salary.
- Adjust allowances and deductions (advances, NSSF, tax) while pending, then mark paid with the M-Pesa/bank
  reference. Paying records a Salaries expense. Staff without `payroll.view` only see their own payslips.

## Farm side
Farmer registration, daily milk records with alerts, feed mills, feed types and market price changes with price
history, credit feed orders stored at the price of the day, payments = litres x price minus credit
(oldest first, never below zero), mark-paid with alert (SMS on paid plans via ``apps/notifications/sms.py``).

## SaaS billing
Starter trial (14 days), Growth, Pro (edit in `apps/tenants/services.py` (`ensure_plans`)). Farmer limits are enforced, SMS is a paid
feature. The owner picks a plan under Billing, gets an invoice with your Paybill and `INVnn`; you confirm
payment on the platform screen (or call `Invoice.mark_paid()` (`apps/tenants/models.py`) from an M-Pesa callback). Expired or suspended
dairies become read-only.

## Payments, SMS, audit, exports, backups, security (new)

### M-Pesa (Daraja)
Two separate M-Pesa accounts are involved:
1. **Your platform account** (env vars `MPESA_*`) collects the dairies' **subscription** payments. The owner
   presses *Pay with M-Pesa* on an invoice, enters the PIN on the phone, and the plan activates automatically
   when Safaricom calls back (the manual *Confirm payment* button remains as a fallback).
2. **Each dairy's own account** (owner enters it under the *M-Pesa* tab; secrets are stored encrypted) is used to
   - **pay farmers and staff** with B2C (single or *Pay all pending via M-Pesa*); an item is marked paid only when
     M-Pesa confirms, and failed sends go back to Pending,
   - **collect feed credit**: farmers (or staff for them) press *Pay with M-Pesa* under Feed store; the money is
     applied to the oldest open credit first. Cash repayments can be recorded too.

Setup: create a Daraja app at developer.safaricom.co.ke; put the Safaricom certificates
(`SandboxCertificate.cer` / `ProductionCertificate.cer`) in `backend/apps/mpesa/certs/`; set `PUBLIC_BASE_URL` to the
public https address of this API (Safaricom must reach `/api/mpesa/...`; use ngrok when testing); start in
**sandbox**, then switch the dairy to production. Callback URLs contain a one-time secret per transaction.
If a B2C request times out, it stays *Sending* until you confirm it manually after checking the M-Pesa statement
(avoids paying twice).

### Africa's Talking SMS
Set `AT_USERNAME`, `AT_API_KEY`, optional `AT_SENDER_ID`. Milk deliveries, credit orders, payments, repayments
and new-login messages are texted to farmers. SMS is a paid-plan feature with a monthly quota per dairy
(`Plan.sms_quota`); every attempt, including skipped ones and why, is in the *SMS log*. Password-reset codes are
not counted against the quota.

### Audit log
Every create/update/delete on farmers, milk, prices, feed, credit, payments, payroll, expenses, roles, members,
M-Pesa settings and invoices is recorded with who, when, IP and the old and new values; logins, failed logins,
exports and M-Pesa callbacks too. Owners and anyone with *View the audit log* see it under *Audit log*;
you see all dairies' roles on the platform screen and everything in `/admin/` (read-only).

### Exports and backups
- *Exports* tab: CSV or PDF for farmers, milk, payments, credit, repayments, expenses and payroll (with date
  range); one-click payslip and milk payment slip PDFs; the owner can download everything as a ZIP.
- **Nightly backup**: `python manage.py backup_db` writes a gzip dump to `BACKUP_DIR`, deletes copies older than
  `BACKUP_KEEP_DAYS` (default 14) and optionally copies to S3 (`BACKUP_S3_BUCKET`, install boto3).
  `docker-compose.yml` runs it every 24 h in the `backup` service (files in `./backups`).
  Restore (Postgres): `gunzip -c backups/maziwa-XXXX.sql.gz | psql -h HOST -U USER -d DB`.
  Also copy backups off the server and test a restore.

### Login security
Login is rate-limited (10/min per IP) and an account locks for 15 minutes after 5 wrong passwords. Passwords must
be 8+ characters and not common or all-numeric. Staff-registered farmers and new team members get a **temporary
password** (farmers also by SMS) and must change it at first login. *Forgot password* sends a 6-digit SMS code
(valid 10 minutes, 5 tries, 3 codes an hour); a reset or password change signs the user out elsewhere. Sessions
expire after `TOKEN_TTL_DAYS` (14). In production set `REDIS_URL` (so limits are shared by all workers),
`TRUST_PROXY=1` behind nginx, and serve over HTTPS (redirect, HSTS and secure cookies turn on with `DEBUG=0`).

### Environment variables
`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `POSTGRES_*`, `REDIS_URL`, `PUBLIC_BASE_URL`,
`BILLING_PAYBILL`, `MPESA_ENV|CONSUMER_KEY|CONSUMER_SECRET|SHORTCODE|PASSKEY`, `MPESA_CERT_SANDBOX|PRODUCTION`,
`AT_USERNAME|API_KEY|SENDER_ID`, `BACKUP_DIR|KEEP_DAYS|S3_BUCKET`, `FIELD_ENCRYPTION_KEY` (Fernet key; derived from
`SECRET_KEY` if empty), `TOKEN_TTL_DAYS`, `TRUST_PROXY`, `SSL_REDIRECT`.

### Upgrading from the previous version
New models and permissions were added (`credit.collect`, `mpesa.manage`, `audit.view`). On a development database,
delete it and every `migrations/` folder and run `makemigrations` and `migrate` again (Animal moved to `herd` and a farmer's route became a link to `collection.Route`, so old migrations no longer fit). Existing dairies' roles
do not gain the new permissions automatically: tick them under *Team and roles*.

## Before going live
Set `SECRET_KEY`, `DEBUG=0`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `BILLING_PAYBILL`; use HTTPS;
build the frontend (`npm run build`); test M-Pesa in sandbox end to end; test a backup restore.
Note: adding an existing username to a dairy gives that person access to that dairy only; consider an
invitation/accept step if you need consent.
