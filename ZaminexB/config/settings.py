import sys
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
#  Configuration
#
#  Settings are plain values edited directly in this file — there is no .env
#  and no dotenv dependency. Change them here for your environment.
# ---------------------------------------------------------------------------

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# Generate a fresh one before deploying:
#   python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
SECRET_KEY = 'django-insecure-v4%ffc(9hsb2v9*npku)syx^s$&v$o%0u&#@ku34pz)#@crb^c'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Add project root to path (safer than adding apps/ directly)
# Rationale: INSTALLED_APPS uses package paths like 'apps.accounts...'.
# Pointing sys.path at BASE_DIR ensures Python can import the top-level
# 'apps' package without shadowing it by injecting BASE_DIR/apps directly.
sys.path.insert(0, str(BASE_DIR))

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.common.apps.CommonConfig',
    'apps.basics.apps.BasicsConfig',
    'apps.accounts.apps.AccountsConfig',
    'apps.listings.apps.ListingsConfig',
    'apps.properties.apps.PropertiesConfig',
    'apps.tasks.apps.TasksConfig',
    'apps.followups.apps.FollowupsConfig',
    'apps.reports.apps.ReportsConfig',
    'rest_framework',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.ArchivedConsultantSessionMiddleware',
    'apps.common.middleware.CurrentUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

# PostgreSQL is the only supported backend. The schema relies on JSONB, partial
# indexes and typed EAV columns, and the reference-data tables assume
# PostgreSQL semantics.
#
# Edit the values below to match your server. A DATABASE_URL environment
# variable, when present, still wins — that is what deployment platforms set —
# but nothing is required for a normal local checkout.
DATABASE_NAME = "zaminex"
DATABASE_USER = "zaminex"
DATABASE_PASSWORD = "zaminex"
DATABASE_HOST = "localhost"
DATABASE_PORT = "5432"

if os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.parse(
            os.environ["DATABASE_URL"],
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": DATABASE_NAME,
            "USER": DATABASE_USER,
            "PASSWORD": DATABASE_PASSWORD,
            "HOST": DATABASE_HOST,
            "PORT": DATABASE_PORT,
            # Re-use connections for 10 minutes instead of opening one per
            # request; a meaningful win on PostgreSQL.
            "CONN_MAX_AGE": 600,
            "CONN_HEALTH_CHECKS": True,
        }
    }

# Fail loudly rather than silently running on an unsupported backend.
# For testing / backup verification we allow SQLite when ALLOW_SQLITE env is set.
if "postgresql" not in DATABASES["default"]["ENGINE"] and not os.environ.get("ALLOW_SQLITE"):
    raise ImproperlyConfigured(
        "Zaminex requires PostgreSQL, but the configured engine is "
        f"'{DATABASES['default']['ENGINE']}'. Check the DATABASE_* values in "
        "config/settings.py."
    )

# Tests build a throwaway database, so behaviour that differs between backends
# (case-insensitive search, JSON handling, constraint enforcement) is exercised
# exactly as in production.
if "test" in sys.argv:
    DATABASES["default"].setdefault("TEST", {})
    DATABASES["default"]["TEST"]["NAME"] = "test_zaminex"


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'fa-ir'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = 'static/'

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Task 3: use custom user model
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"

LOGOUT_REDIRECT_URL = "/accounts/login/"

# Task 4: media settings
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Account-scoped login protection: 5 failed attempts in 15 minutes => 10-minute lock.
LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
LOGIN_LOCKOUT_SECONDS = 10 * 60

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "apps.common.exceptions.persian_exception_handler",
}
