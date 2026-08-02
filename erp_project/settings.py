""" - ERP System Settings
Designer: YangEra
"""
from decouple import config

from pathlib import Path
import os
import sys

FROZEN = getattr(sys, 'frozen', False)

if FROZEN:
    BASE_DIR = Path(os.path.dirname(sys.executable))
    BUNDLE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = BASE_DIR

SECRET_KEY = 'django-erp-fayaz-secret-key-change-in-production-xyz123'

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost').split(',')



# ============================================================
# INSTALLED APPS
# ============================================================
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
]

LOCAL_APPS = [
    'apps.core',
    'apps.accounts',
    'apps.dashboard',
    'apps.inventory', 
    'apps.warehouse',
    'apps.customers',
    'apps.sales',
    'apps.suppliers',
    'apps.purchases',
    'apps.expenses',
    'apps.currency',
    'apps.banker',
    'apps.reports',
    'apps.alerts', 
    'apps.backup_system',
    'apps.activity_logs',  # ← ADD
    'apps.settings_app',
    'apps.capital',
    'apps.loans'
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

# ============================================================
# MIDDLEWARE
# ============================================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.activity_logs.middleware.ActivityLogMiddleware',  # ← UPDATED
    'apps.core.middleware.TimezoneMiddleware',
]

ROOT_URLCONF = 'erp_project.urls'

# ============================================================
# TEMPLATES
# ============================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BUNDLE_DIR / 'templates', BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.site_settings',    # Global context
                'apps.core.context_processors.sidebar_context',  # Sidebar data
            ],
        },
    },
]

WSGI_APPLICATION = 'erp_project.wsgi.application'

# ============================================================
# DATABASE
# ============================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': Path(os.environ.get('DB_PATH', str(BASE_DIR / 'db' / 'YangEraDB.sqlite3'))),
        'OPTIONS': {
            'timeout': 30,
        },
    }
}

# ============================================================
# AUTH
# ============================================================
AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 6}},
]

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

SESSION_COOKIE_AGE = 86400 * 30     # 30 days
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# ============================================================
# LOCALIZATION — AFGHANISTAN
# ============================================================
LANGUAGE_CODE = 'fa'
TIME_ZONE = 'Asia/Kabul'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# ============================================================
# STATIC FILES (offline — no CDN)
# ============================================================
STATIC_URL = '/static/'
STATIC_ROOT = Path(os.environ.get('STATIC_ROOT_OVERRIDE', str(BASE_DIR / 'staticfiles')))
STATICFILES_DIRS = [] if FROZEN else [BASE_DIR / 'static']

STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ══════════════════════════════════════════════════════════════
# PRODUCTION SECURITY (set DEBUG=False in production)
# ══════════════════════════════════════════════════════════════
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'SAMEORIGIN'  # Allow iframes within same site for print
    SESSION_COOKIE_SECURE = False   # False for local HTTP
    CSRF_COOKIE_SECURE = False      # False for local HTTP

# ══════════════════════════════════════════════════════════════
# PERFORMANCE
# ══════════════════════════════════════════════════════════════
# Cache (in-memory for offline use)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'erp-taimourian-cache',
    }
}

# ══════════════════════════════════════════════════════════════
# FILE UPLOAD
# ══════════════════════════════════════════════════════════════
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB

# ============================================================
# DEFAULT PRIMARY KEY
# ============================================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================================
# BUSINESS SETTINGS
# ============================================================
BUSINESS_NAME = 'یانگ‌ایرا راهکارهای فناوری'
BUSINESS_NAME_EN = 'YangEra Tech solutions'
DESIGNER_CREDIT = 'YangEra'
BUSINESS_PHONE_1 = '0791810095'
# BUSINESS_PHONE_2 = '0705294629'
# BUSINESS_ADDRESS = 'هرات کوچه گدام مجتمع تجارتی تیموریان'
DEFAULT_CURRENCY = 'AFN'

# ============================================================
# MESSAGES
# ============================================================
from django.contrib.messages import constants as messages
MESSAGE_TAGS = {
    messages.DEBUG: 'secondary',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}

# Ensure db directory exists
import os
os.makedirs(BASE_DIR / 'db', exist_ok=True)
os.makedirs(BASE_DIR / 'media', exist_ok=True)

# Backup directory
import os
BACKUP_DIR = BASE_DIR / 'backup_system'
os.makedirs(BACKUP_DIR, exist_ok=True)
BACKUP_KEEP_LAST = 30  # Keep last 30 backup_system

# Activity log settings
ACTIVITY_LOG_RETENTION_DAYS = 90  # Keep logs for 90 days
ACTIVITY_LOG_ENABLED = True