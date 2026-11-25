import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load the .env file from the root 'IS project' directory and BASE_DIR
# override=True ensures the .env values always win, even if the shell
# happens to have empty/stale env vars already set.
load_dotenv(BASE_DIR.parent / '.env', override=True)
load_dotenv(BASE_DIR / '.env', override=True)

# Quick-start development settings - unsuitable for production
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-3=--=z#=7eam7q5e#^2s=$pc7098nc-9ja91nx=yqive(d5!ig')

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party apps
    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    # Local apps
    'users.apps.UsersConfig',
    'tasks.apps.TasksConfig',
    'payments.apps.PaymentsConfig',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'domesticplatform_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR.parent / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'domesticplatform_backend.wsgi.application'

# Database configuration
DB_NAME = os.environ.get('DB_NAME')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')

if DB_NAME and DB_USER:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': DB_HOST,
            'PORT': DB_PORT,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
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

# Custom User Model configuration
AUTH_USER_MODEL = 'users.CustomUser'

# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# CORS settings
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Broadcast-matching configuration
BROADCAST_ROUND1_RADIUS_KM = 50      # wide radius — no GPS on most users yet
BROADCAST_ROUND2_RADIUS_KM = 100
BROADCAST_ROUND1_MIN_RATING = 0      # accept all verified students
BROADCAST_ROUND2_ROUND2_MIN_RATING = 0
BROADCAST_ROUND_SIZE = 10            # send to top 10 students per round
BROADCAST_ROUND_TIMEOUT = 600
BROADCAST_GRACE_WINDOW = 600

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'

# Media files (uploaded photos)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Cancellation policy defaults (overridable via Django admin or /api/cancellation-policy/)
CANCELLATION_FREE_BEFORE_HOURS = 24    # free cancellation if >24h before scheduled start
CANCELLATION_PARTIAL_REFUND_PCT = 80   # 80% refund if cancelling within 24h

# ---------------------------------------------------------------------------
# Test-suite speed
# ---------------------------------------------------------------------------
# PBKDF2 (1.5M iterations) dominates test runtime: every setUp() creates
# several users and each password hash takes ~1-2 s.  During `manage.py test`
# only, switch to a fast (insecure) hasher — the standard Django technique
# (https://docs.djangoproject.com/en/stable/topics/testing/overview/#speeding-up-tests).
if len(sys.argv) > 1 and sys.argv[1] == 'test':
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'