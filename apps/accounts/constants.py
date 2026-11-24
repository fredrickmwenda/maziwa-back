"""Permission codes and the default roles every new dairy gets."""
KIND_OWNER, KIND_FARMER, KIND_CUSTOM = "OWNER", "FARMER", "CUSTOM"


PERMISSIONS = {
    "farmers.view": "View farmers",
    "farmers.manage": "Register and edit farmers",
    "milk.view": "View milk records",
    "milk.record": "Record milk deliveries",
    "rates.manage": "Set the milk price",
    "store.view": "View the feed store",
    "store.manage": "Manage products, feed mills, stock and feed prices",
    "orders.create": "Sell feed on credit",
    "payments.view": "View farmer payments",
    "payments.manage": "Calculate farmer payments and mark them paid",
    "expenses.view": "View expenses",
    "expenses.manage": "Record expenses",
    "payroll.view": "View all payroll",
    "payroll.manage": "Run payroll and pay staff",
    "team.manage": "Manage users and roles",
    "billing.manage": "Manage the subscription",
    "credit.collect": "Receive feed credit repayments (cash or M-Pesa)",
    "mpesa.manage": "Manage M-Pesa settings and see M-Pesa transactions",
    "audit.view": "View the audit log and SMS log",
    "advances.view": "View cash advances and loans",
    "advances.request": "Request an advance",
    "advances.manage": "Approve and pay advances, set advance rules",
    "herd.view": "View animals, health records and milk per cow",
    "herd.manage": "Record animals, health events and milk per cow",
    "sales.view": "View milk sales and buyers",
    "sales.manage": "Record milk sales and money received",
    "pos.sell": "Make cash sales at the feed store",
    "reports.view": "View reports and financial summaries",
    "routes.view": "View collection centres, routes, transporters and route sheets",
    "routes.manage": "Manage centres, routes and transporters; open and receive route sheets; pay transporters",
}


FARMER_PERMS = ["farmers.view", "milk.view", "payments.view", "store.view", "orders.create",
                "advances.view", "advances.request", "herd.view", "herd.manage"]


DEFAULT_ROLES = [
    ("Owner", KIND_OWNER, list(PERMISSIONS)),
    ("Manager", KIND_CUSTOM, [c for c in PERMISSIONS if c not in ("team.manage", "billing.manage", "mpesa.manage")]),
    ("Milk Clerk", KIND_CUSTOM, ["farmers.view", "milk.view", "milk.record", "herd.view",
                                  "routes.view", "routes.manage"]),
    ("Store Keeper", KIND_CUSTOM, ["farmers.view", "store.view", "store.manage", "orders.create", "credit.collect", "pos.sell"]),
    ("Accountant", KIND_CUSTOM, ["farmers.view", "milk.view", "payments.view", "payments.manage",
                                 "expenses.view", "expenses.manage", "payroll.view", "payroll.manage", "credit.collect",
                                 "advances.view", "advances.manage", "sales.view", "sales.manage", "reports.view", "routes.view"]),
    ("Farmer", KIND_FARMER, FARMER_PERMS),
]
