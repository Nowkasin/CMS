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
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in config('DJANGO_CSRF_TRUSTED_ORIGINS', default='').split(',') if o.strip()
]

# รองรับการวางระบบใต้ URL prefix เช่น https://server.example/cms/
# URLconf จะรับ prefix นี้โดยตรง จึงใช้ได้ทั้ง runserver และ Web server ที่ส่ง
# path /cms/... เข้า Django โดยไม่ตัด prefix ออก
_script_name_value = config('DJANGO_SCRIPT_NAME', default='').strip().strip('/')
URL_PREFIX = _script_name_value
SCRIPT_NAME_PREFIX = f'/{_script_name_value}' if _script_name_value else ''

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',   # จำเป็น: ใช้เก็บข้อมูล staged ระหว่าง step ของ wizard
    'django.contrib.staticfiles',
    'meters',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',  # จำเป็นสำหรับ request.session
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # ทุกหน้าต้องล็อกอิน ยกเว้น view ที่ติด @login_not_required
    'django.contrib.auth.middleware.LoginRequiredMiddleware',
    # ตรวจสิทธิ์เมนูจาก Session ซ้ำฝั่ง Server ป้องกันการพิมพ์ URL เข้าโดยตรง
    'meters.permission_middleware.CMSMenuPermissionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'meters.log_middleware.ActivityLogMiddleware',
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
                'django.contrib.auth.context_processors.auth',
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
        # session ของ wizard นำเข้า Excel ใหญ่ได้หลาย MB และ SQLite ล็อกทั้งไฟล์ตอนเขียน
        # ถ้ามีหลาย worker/ผู้ใช้พร้อมกันจะเจอ "database is locked" ได้ จึง:
        #   WAL           -- ผู้อ่านไม่ถูกบล็อกระหว่างมีคนเขียน
        #   IMMEDIATE     -- ขอล็อกเขียนตั้งแต่ต้นทรานแซกชัน (กัน deadlock แบบ upgrade lock)
        #   timeout 20 วิ -- รอคิวแทนการ error ทันที
        'OPTIONS': {
            'timeout': 20,
            'transaction_mode': 'IMMEDIATE',
            'init_command': 'PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;',
        },
    }
}

# -----------------------------------------------------------------------
# Cache -- ใช้นับจำนวนครั้งล็อกอินผิด (meters/views/auth.py)
# ต้องเป็น cache ที่ทุก worker เห็นร่วมกัน ค่าเริ่มต้นของ Django (LocMemCache) แยกต่อ process
# จึงใช้ FileBasedCache (ไม่ต้องสร้างตารางเพิ่ม) -- ถ้ารันหลายเครื่องให้เปลี่ยนเป็น redis
# -----------------------------------------------------------------------
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': config('DJANGO_CACHE_DIR', default=str(BASE_DIR / 'var' / 'cache')),
    }
}

LANGUAGE_CODE = 'th'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

STATIC_URL = f'{SCRIPT_NAME_PREFIX}/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# -----------------------------------------------------------------------
# ขีดจำกัดการอัปโหลดไฟล์ Excel (ใช้ที่ meters/forms.py และ views/steppage.py)
#
# สองค่าข้างบนของ Django ไม่ใช่ขีดจำกัดขนาดไฟล์:
#   DATA_UPLOAD_MAX_MEMORY_SIZE คุมขนาด POST ที่ไม่ใช่ไฟล์
#   FILE_UPLOAD_MAX_MEMORY_SIZE เป็นเกณฑ์ว่าจะเก็บใน RAM หรือเขียนเป็นไฟล์ชั่วคราว
# ไฟล์ 500 MB จึงผ่านทั้งคู่ แล้วไปล้มที่ openpyxl -- ต้องจำกัดเองที่ฟอร์ม
#
# EXCEL_UPLOAD_MAX_ROWS จำกัดจำนวนแถวที่ parse ได้ เพราะข้อมูล staged ถูกเก็บใน
# session (ตาราง django_session ใน SQLite) วัดแล้วประมาณ 650 ไบต์ต่อแถว
# -> 5,000 แถว ประมาณ 3 MB ต่อ session ซึ่งยังรับได้
# ข้อมูลจริงมีมิเตอร์ 52 ตัว พื้นที่ย่อย 469 รายการ ไฟล์ปกติจึงไม่ใกล้เพดานนี้
# -----------------------------------------------------------------------
EXCEL_UPLOAD_MAX_SIZE = 10 * 1024 * 1024
EXCEL_UPLOAD_MAX_ROWS = 5000

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 60 * 60 * 2  # 2 ชั่วโมง พอสำหรับทำ wizard ให้จบ
SESSION_COOKIE_PATH = f'{SCRIPT_NAME_PREFIX}/' if SCRIPT_NAME_PREFIX else '/'
CSRF_COOKIE_PATH = SESSION_COOKIE_PATH

# -----------------------------------------------------------------------
# ความปลอดภัยเมื่อเปิดใช้ผ่าน HTTPS (Production)
#
# DJANGO_HTTPS=True       -- ส่ง cookie session/CSRF เฉพาะ HTTPS และเปิด HSTS
#   ค่าเริ่มต้นเป็น False เพราะถ้าเปิดบนเครื่องที่ยังเป็น HTTP จะล็อกอินไม่ได้เลย
#   (เบราว์เซอร์ไม่ส่ง secure cookie กลับมา)
# DJANGO_BEHIND_PROXY=True -- IIS/Nginx รับ HTTPS แล้วส่งต่อเป็น HTTP ให้ Django
#   ต้องเปิดเพื่อให้ request.is_secure() ถูก -- เปิดเฉพาะเมื่อ proxy ตั้ง
#   X-Forwarded-Proto เองเสมอ ไม่งั้น client ปลอม header ได้
# -----------------------------------------------------------------------
USE_HTTPS = config('DJANGO_HTTPS', default=False, cast=bool)
SESSION_COOKIE_SECURE = USE_HTTPS
CSRF_COOKIE_SECURE = USE_HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'
if USE_HTTPS:
    SECURE_HSTS_SECONDS = config('DJANGO_HSTS_SECONDS', default=3600, cast=int)
if config('DJANGO_BEHIND_PROXY', default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = True

# -----------------------------------------------------------------------
# Logging -- โค้ดหลายจุดพึ่ง logger.exception() แทนการโชว์ error ดิบบนหน้าเว็บ
# (นำเข้า Excel ล้ม, เขียน activity log ไม่สำเร็จ, ตรวจสิทธิ์ล้ม) จึงต้องลงไฟล์ให้ย้อนดูได้
# ไฟล์หมุนเวียนวันละไฟล์ เก็บ 30 วัน -- ห้าม log รหัสผ่าน/ข้อมูลใน .env (ดู AGENTS.md)
# -----------------------------------------------------------------------
LOG_DIR = Path(config('DJANGO_LOG_DIR', default=str(BASE_DIR / 'var' / 'logs')))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_LEVEL = config('DJANGO_LOG_LEVEL', default='INFO')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s %(levelname)s %(name)s: %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
        'file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': str(LOG_DIR / 'cms.log'),
            'when': 'midnight',
            'backupCount': 30,
            'encoding': 'utf-8',
            # หลาย worker เขียนไฟล์เดียวกันได้ แต่การหมุนไฟล์ตอนเที่ยงคืนอาจชนกัน
            # delay=True เปิดไฟล์ตอนเขียนครั้งแรก ลดการถือ handle ค้าง
            'delay': True,
            'formatter': 'standard',
        },
    },
    'loggers': {
        'meters': {
            'handlers': ['console', 'file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# -----------------------------------------------------------------------
# Authentication
#
# LDAP ตรวจรหัสผ่าน ส่วนตาราง SysUserGroupAssiciate/SysGroup ใน SQL Server เดิม
# ใช้ยืนยันว่าบุคคลนั้นมีสิทธิ์เข้า CMS รหัสผ่านจะไม่ถูกเก็บในระบบนี้
# -----------------------------------------------------------------------
AUTHENTICATION_BACKENDS = ['meters.auth_backend.BuasriLDAPBackend']
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'meter_list'
LOGOUT_REDIRECT_URL = 'login'

# ดึงสิทธิ์เมนูจาก K2 ใหม่ทุกกี่วินาทีระหว่างที่ผู้ใช้ยังล็อกอินอยู่ (0 = ไม่ดึงใหม่ ใช้ค่าตอนล็อกอิน)
CMS_ACCESS_REFRESH_SECONDS = config('CMS_ACCESS_REFRESH_SECONDS', default=600, cast=int)

LDAP_SERVER_URI = config('LDAP_SERVER_URI', default='')
LDAP_USER_DN_TEMPLATE = config('LDAP_USER_DN_TEMPLATE', default='')
LDAP_CONNECT_TIMEOUT = config('LDAP_CONNECT_TIMEOUT', default=5, cast=int)
LDAP_START_TLS = config('LDAP_START_TLS', default=False, cast=bool)
LDAP_TLS_VALIDATE = config('LDAP_TLS_VALIDATE', default=True, cast=bool)
LDAP_USERNAME_PATTERN = config(
    'LDAP_USERNAME_PATTERN',
    default=r'^[A-Za-z0-9._-]{1,64}$',
)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
