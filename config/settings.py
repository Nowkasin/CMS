"""
Django settings สำหรับโปรเจกต์ contract_meter_django

ค่าที่ sensitive ทั้งหมด (secret key, รหัสผ่าน DB, host) อ่านจากไฟล์ .env
ผ่าน django-environ ไม่ hardcode ไว้ในโค้ดเด็ดขาด
"""
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)
env_file = BASE_DIR / '.env'
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env('DJANGO_SECRET_KEY')
DEBUG = env.bool('DJANGO_DEBUG', default=False)
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'meters',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
]

ROOT_URLCONF = 'config.urls'

# template อยู่ที่ระดับโปรเจกต์ (templates/meters/*.html) ไม่ใช่ข้างใน meters/ app
# package โดยตรง จึงต้องระบุ DIRS ให้ชัดเจน (APP_DIRS อย่างเดียวหาไม่เจอ)
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
# ฐานข้อมูล: ต่อ SQL Server จริง (SWU_contract) ผ่าน mssql-django
# ทุกค่าอ่านจาก .env ทั้งหมด ไม่มีค่า default ที่เป็นความลับอยู่ในนี้
# -----------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'),
        'PORT': env('DB_PORT', default='1433'),
        'OPTIONS': {
            'driver': env('DB_ODBC_DRIVER', default='ODBC Driver 17 for SQL Server'),
        },
    }
}

LANGUAGE_CODE = 'th'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

# ไฟล์ static อยู่ที่ระดับโปรเจกต์เช่นกัน (static/meters/css, static/meters/js)
# ไม่ใช่ข้างใน meters/ app package โดยตรง จึงต้องระบุ STATICFILES_DIRS ให้ชัดเจน
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -----------------------------------------------------------------------
# Session: จำกัดอายุไว้ไม่ให้ session ทดสอบเก่าค้างอยู่นาน (ที่เจอปัญหาไปก่อนหน้านี้
# ว่าเข้า /review/ หรือ /confirm/ ตรงๆ แล้วมีข้อมูลทดสอบเก่าค้างอยู่)
# หมดอายุอัตโนมัติเมื่อปิดเบราว์เซอร์ และอย่างช้าไม่เกิน 8 ชั่วโมงแม้ไม่ปิดเบราว์เซอร์
# -----------------------------------------------------------------------
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 60 * 1  # 1 ชั่วโมง