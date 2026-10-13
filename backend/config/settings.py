"""Django settings for AAWEN (عاون).

All environment-specific values come from environment variables (see ../.env.example).
AAWEN_ENV is one of: development, test, production.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

AAWEN_ENV = env("AAWEN_ENV", default="development")
IS_PRODUCTION = AAWEN_ENV == "production"
IS_TEST = AAWEN_ENV == "test"

DEBUG = env.bool("DEBUG", default=not IS_PRODUCTION)
if IS_PRODUCTION:
    SECRET_KEY = env("SECRET_KEY")  # mandatory, no default in production
    if len(SECRET_KEY) < 50:
        raise environ.ImproperlyConfigured("SECRET_KEY must be at least 50 characters in production")
    DEBUG = False
else:
    SECRET_KEY = env("SECRET_KEY", default="dev-only-insecure-key-do-not-use-in-production-0123456789abcdef")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "testserver"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django.contrib.postgres",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.geo",
    "apps.agencies",
    "apps.reports",
    "apps.roadnow",
    "apps.community",
    "apps.inventory",
    "apps.finance",
    "apps.notifications",
    "apps.ai",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

DATABASES = {"default": env.db("DATABASE_URL", default="postgis://aawen:devpass@localhost:5432/aawen")}
DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = (
    ["django.contrib.auth.hashers.MD5PasswordHasher"] if IS_TEST
    else ["django.contrib.auth.hashers.PBKDF2PasswordHasher", "django.contrib.auth.hashers.ScryptPasswordHasher"]
)

LANGUAGE_CODE = "ar"
LANGUAGES = [("ar", "العربية"), ("en", "English")]
TIME_ZONE = "Africa/Tripoli"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media-private/"  # never served directly; files go through permission-checked views
MEDIA_ROOT = env.path("MEDIA_ROOT", default=str(BASE_DIR / "var" / "media"))

# --- Media storage: local filesystem in development, S3-compatible (MinIO / AWS / R2) when configured
USE_S3 = env.bool("USE_S3", default=False)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
if USE_S3:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("S3_BUCKET"),
            "endpoint_url": env("S3_ENDPOINT_URL", default=None),
            "access_key": env("S3_ACCESS_KEY"),
            "secret_key": env("S3_SECRET_KEY"),
            "region_name": env("S3_REGION", default="us-east-1"),
            "default_acl": "private",
            "querystring_auth": True,
            "querystring_expire": 600,
            "file_overwrite": False,
        },
    }

# --- Upload limits
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
AAWEN_MAX_IMAGE_BYTES = env.int("MAX_IMAGE_BYTES", default=10 * 1024 * 1024)
AAWEN_MAX_AUDIO_BYTES = env.int("MAX_AUDIO_BYTES", default=6 * 1024 * 1024)
AAWEN_MAX_DOC_BYTES = env.int("MAX_DOC_BYTES", default=10 * 1024 * 1024)
AAWEN_IMAGE_MAX_SIDE = 1600

# --- REST framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend",
                                "rest_framework.filters.OrderingFilter"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.Pagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="120/min"),
        "user": env("THROTTLE_USER", default="300/min"),
        "otp": env("THROTTLE_OTP", default="5/hour"),
        "login": env("THROTTLE_LOGIN", default="10/hour"),
        "report_submit": env("THROTTLE_REPORT", default="30/hour"),
        "upload": env("THROTTLE_UPLOAD", default="60/hour"),
        "road_alert": env("THROTTLE_ROAD", default="30/hour"),
        "vote": env("THROTTLE_VOTE", default="120/hour"),
        "webhook": "600/min",
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=30)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AAWEN API — واجهة برمجة عاون",
    "DESCRIPTION": "Community civic-participation platform for Libya (Tripoli first).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173", "http://127.0.0.1:5173"])
CORS_ALLOW_HEADERS = ["accept", "authorization", "content-type", "idempotency-key", "accept-language", "x-client-version"]

# --- Celery (Redis broker)
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_EAGER", default=IS_TEST)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "expire-road-alerts": {"task": "apps.roadnow.tasks.expire_alerts", "schedule": 60.0},
    "followup-reviews": {"task": "apps.reports.tasks.schedule_followups", "schedule": 3600.0},
    "recompute-priorities": {"task": "apps.reports.tasks.recompute_priorities", "schedule": 3600.0},
    "referral-escalations": {"task": "apps.reports.tasks.escalate_unacknowledged", "schedule": 3600.0},
    "overdue-returns": {"task": "apps.inventory.tasks.mark_overdue", "schedule": 3600.0},
    "process-deletions": {"task": "apps.accounts.tasks.process_deletion_requests", "schedule": 3600.0},
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                      "LOCATION": env("CACHE_URL", default="redis://localhost:6379/1")}}
if IS_TEST:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- External integrations (all optional; explicit simulators in development)
SMS_PROVIDER = env("SMS_PROVIDER", default="console" if not IS_PRODUCTION else "disabled")  # console|http|disabled
SMS_HTTP_URL = env("SMS_HTTP_URL", default="")
SMS_HTTP_TOKEN = env("SMS_HTTP_TOKEN", default="")
SMS_SENDER_ID = env("SMS_SENDER_ID", default="AAWEN")
PUSH_PROVIDER = env("PUSH_PROVIDER", default="simulated" if not IS_PRODUCTION else "disabled")  # fcm|simulated|disabled
FCM_PROJECT_ID = env("FCM_PROJECT_ID", default="")
FCM_SERVICE_ACCOUNT_FILE = env("FCM_SERVICE_ACCOUNT_FILE", default="")
AI_PROVIDER = env("AI_PROVIDER", default="local")  # local|anthropic
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
AI_MODEL = env("AI_MODEL", default="claude-haiku-5-5")
TRANSCRIPTION_PROVIDER = env("TRANSCRIPTION_PROVIDER", default="none")  # none|simulated|http
TRANSCRIPTION_HTTP_URL = env("TRANSCRIPTION_HTTP_URL", default="")

# Payments: 'disabled' (default, production), 'simulated' (development/test), 'live' (needs provider + beneficiary + authorisation)
PAYMENTS_MODE = env("PAYMENTS_MODE", default="disabled" if IS_PRODUCTION else "simulated")
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="simulator")
PAYMENT_WEBHOOK_SECRET = env("PAYMENT_WEBHOOK_SECRET", default="" if IS_PRODUCTION else "dev-simulator-webhook-secret")
PAYMENT_BENEFICIARY_CONFIGURED = env.bool("PAYMENT_BENEFICIARY_CONFIGURED", default=False)
PAYMENT_LIVE_AUTHORISED = env.bool("PAYMENT_LIVE_AUTHORISED", default=False)
PAYMENT_HTTP_BASE_URL = env("PAYMENT_HTTP_BASE_URL", default="")
PAYMENT_HTTP_API_KEY = env("PAYMENT_HTTP_API_KEY", default="")
PLATFORM_FEE_PERCENT = env.float("PLATFORM_FEE_PERCENT", default=0.0)

DEMO_DATA_ALLOWED = env.bool("DEMO_DATA_ALLOWED", default=not IS_PRODUCTION)
PUBLIC_WEB_URL = env("PUBLIC_WEB_URL", default="http://localhost:5173")
BACKUP_DIR = env.path("BACKUP_DIR", default=str(BASE_DIR / "var" / "backups"))

# --- Security hardening
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
if IS_PRODUCTION:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}
