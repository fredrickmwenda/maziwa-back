import os
from pathlib import Path

from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env for local dev / bare-metal. In Docker the vars arrive via the
# compose `environment:` block, so this call is simply a no-op there.
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

env = os.environ.get


def env_bool(name: str, default: str = "0") -> bool:
    return env(name, default).strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list[str]:
    return [v.strip() for v in env(name, default).split(",") if v.strip()]


def env_int(name: str, default: str) -> int:
    return int(env(name, default))


# ---------------------------------------------------------------- core ----
SECRET_KEY = env("SECRET_KEY", "dev-only-change-me")
DEBUG = env_bool("DEBUG", "1")
if not DEBUG and SECRET_KEY == "dev-only-change-me":
    raise RuntimeError("Set a real SECRET_KEY when DEBUG=0")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "*")
if not DEBUG and "*" in ALLOWED_HOSTS:
    raise RuntimeError("ALLOWED_HOSTS must be explicit when DEBUG=0")

FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", "")   # Fernet key; derived from SECRET_KEY if empty
TRUST_PROXY = env_bool("TRUST_PROXY", "0")

# ---------------------------------------------------------------- apps ----
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "rest_framework.authtoken", "corsheaders",
    "core.apps.CoreConfig",
    "apps.tenants.apps.TenantsConfig",
    "apps.collection.apps.CollectionConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.farmers.apps.FarmersConfig",
    "apps.milk.apps.MilkConfig",
    "apps.store.apps.StoreConfig",
    "apps.payments.apps.PaymentsConfig",
    "apps.payroll.apps.PayrollConfig",
    "apps.expenses.apps.ExpensesConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.mpesa.apps.MpesaConfig",
    "apps.audit.apps.AuditConfig",
    "apps.advances.apps.AdvancesConfig",
    "apps.herd.apps.HerdConfig",
    "apps.sales.apps.SalesConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.audit.middleware.AuditMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------- database ----
if env("POSTGRES_DB"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER", "postgres"),
        "PASSWORD": env("POSTGRES_PASSWORD", ""),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", "60"),
        "OPTIONS": {"connect_timeout": 5},
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
                             "NAME": BASE_DIR / "db.sqlite3"}}

# ---------------------------------------------------------------- cache ----
# Throttling + login lockout need a cache shared by all workers → Redis.
if env("REDIS_URL"):
    CACHES = {"default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
    }}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# ---------------------------------------------------------------- auth ----
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

TIME_ZONE = "Africa/Nairobi"
USE_TZ = True

LANGUAGE_CODE = "en-us"
USE_I18N = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- CORS / CSRF ----
CORS_ALLOW_HEADERS = list(default_headers) + ["x-dairy"]
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", ",".join(CORS_ALLOWED_ORIGINS))

# ---------------------------------------------------------------- DRF ----
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.audit.authentication.AuditTokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "120/min", "user": "1200/min",
                               "login": "10/min", "reset": "5/hour"},
    **({"NUM_PROXIES": 1} if TRUST_PROXY else {}),
}

TOKEN_TTL_DAYS = env_int("TOKEN_TTL_DAYS", "14")

# ---------------------------------------------------------------- HTTPS ----
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SSL_REDIRECT", "1")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------- SaaS billing ----
BILLING_PAYBILL = env("BILLING_PAYBILL", "000000")
TRIAL_DAYS = env_int("TRIAL_DAYS", "14")
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", "").rstrip("/")

# ---------------------------------------------------------------- Daraja (platform) ----
MPESA_PLATFORM = {
    "env": env("MPESA_ENV", "sandbox"),
    "consumer_key": env("MPESA_CONSUMER_KEY", ""),
    "consumer_secret": env("MPESA_CONSUMER_SECRET", ""),
    "shortcode": env("MPESA_SHORTCODE", ""),
    "passkey": env("MPESA_PASSKEY", ""),
}
MPESA_CERT_SANDBOX = env(
    "MPESA_CERT_SANDBOX",
    str(BASE_DIR / "apps" / "mpesa" / "certs" / "SandboxCertificate.cer"),
)
MPESA_CERT_PRODUCTION = env(
    "MPESA_CERT_PRODUCTION",
    str(BASE_DIR / "apps" / "mpesa" / "certs" / "ProductionCertificate.cer"),
)

# ---------------------------------------------------------------- Africa's Talking ----
AT_USERNAME = env("AT_USERNAME", "sandbox")
AT_API_KEY = env("AT_API_KEY", "")
AT_SENDER_ID = env("AT_SENDER_ID", "")

# ---------------------------------------------------------------- backups ----
BACKUP_DIR = env("BACKUP_DIR", str(BASE_DIR / "backups"))
BACKUP_KEEP_DAYS = env_int("BACKUP_KEEP_DAYS", "14")
BACKUP_S3_BUCKET = env("BACKUP_S3_BUCKET", "")

# ---------------------------------------------------------------- logging ----
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "std": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "std"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO"), "propagate": False},
    },
}
