"""
Django settings สำหรับโปรเจกต์ CMS

หมายเหตุสถาปัตยกรรม: ข้อมูลธุรกิจจริง (มิเตอร์/สัญญา/พื้นที่) ไม่ได้ผ่าน Django ORM
แต่คุยกับ SQL Server ตรงๆ ผ่าน pyodbc ใน meters/services.py (อ่านค่าเชื่อมต่อจาก .env
ด้วย python-decouple) ดังนั้น DATABASES ด้านล่างนี้ใช้ SQLite แยกต่างหาก
มีไว้แค่สำหรับกลไกภายในของ Django เอง (Session สำหรับเก็บข้อมูล staged
ระหว่าง step ของ wizard) เท่านั้น ไม่เกี่ยวกับข้อมูลจริง
"""
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('DJANGO_SECRET_KEY')
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('DJANGO_ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.sessions',   # จำเป็น: ใช้เก็บข้อมูล staged ระหว่าง step ของ wizard
    'django.contrib.staticfiles',
    'meters',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',  # จำเป็นสำหรับ request.session
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# -----------------------------------------------------------------------
# DB ของ Django เอง (ใช้แค่เก็บ session) - ไม่ใช่ SQL Server ธุรกิจจริง
# ข้อมูลจริงต่อผ่าน pyodbc ใน meters/services.py แยกต่างหาก อ่านค่าจาก .env
# (DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_ODBC_DRIVER)
# -----------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

LANGUAGE_CODE = 'th'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 60 * 60 * 2  # 2 ชั่วโมง พอสำหรับทำ wizard ให้จบ

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'