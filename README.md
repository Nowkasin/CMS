# CMS -- ระบบมิเตอร์น้ำ-ไฟ x สัญญา

เว็บแอป Django สำหรับจัดการทะเบียนมิเตอร์น้ำ-ไฟ นำเข้า/ดาวน์โหลดไฟล์ Excel เลขอ่านมิเตอร์
งานยกเลิกสัญญา และประวัติการใช้งาน ข้อมูลธุรกิจอยู่ใน SQL Server เดิม (อ่าน/เขียนผ่าน pyodbc
และ stored procedure) ส่วน SQLite ใช้แค่กับ session/ผู้ใช้ของ Django เอง

## โครงสร้างโปรเจกต์

```
CMS/
├── manage.py
├── requirements.txt
├── config/
│   ├── settings.py            -- อ่านค่าทั้งหมดจาก .env ผ่าน python-decouple
│   └── urls.py                -- รองรับ URL prefix (DJANGO_SCRIPT_NAME)
├── meters/
│   ├── auth_backend.py        -- ล็อกอินด้วย Buasri LDAP + อ่านสิทธิ์จาก K2
│   ├── permissions.py         -- map สิทธิ์เมนู K2 กับ URL + เก็บสิทธิ์ลง session
│   ├── permission_middleware.py -- บังคับสิทธิ์ทุก request และดึงสิทธิ์ใหม่จาก K2 เป็นระยะ
│   ├── log_middleware.py      -- ลง activity log ของทุกการกระทำผ่านหน้าเว็บ (ดูหัวไฟล์)
│   ├── signals.py             -- log เข้า/ออกระบบ
│   ├── utils.py               -- วันที่ไทย/พ.ศ. และการแปลงค่าจากฟอร์ม (ใช้ร่วมหลาย view)
│   ├── forms.py               -- ตรวจไฟล์ Excel ที่อัปโหลด
│   ├── services/              -- SQL ทั้งหมดอยู่ที่นี่ (ห้ามเขียน SQL ใน view)
│   │   ├── db.py              -- เปิด connection SQL Server
│   │   ├── access.py          -- ตัวตน/กลุ่ม/เมนูจาก K2 (อ่านอย่างเดียว)
│   │   ├── excel_import.py    -- อ่านไฟล์ Excel เป็นแถว staged (Step 1)
│   │   ├── meter_import.py    -- บันทึกแถว staged ลง DB ในทรานแซกชันเดียว (Step 3)
│   │   ├── meters.py          -- ทะเบียนมิเตอร์ / พื้นที่ย่อย / เลขอ่าน
│   │   ├── termination.py     -- ยกเลิกสัญญา
│   │   ├── download.py        -- ข้อมูลไฟล์ดาวน์โหลด Excel
│   │   ├── excel_export.py    -- ไฟล์ส่งออกจากแดชบอร์ด
│   │   ├── phase.py           -- Master ระบบไฟฟ้า
│   │   ├── activity_log.py    -- อ่าน/เขียน Contract_activity_log
│   │   └── sql_utils.py       -- ตัวช่วยประกอบ SQL (LIKE pattern)
│   ├── views/                 -- แยกไฟล์ตามเมนู (ดู views/__init__.py)
│   └── tests/                 -- test อัตโนมัติ (ไม่ต่อ SQL Server จริง)
├── templates/meters/
├── static/meters/
└── var/                       -- log และ cache ที่ระบบสร้างตอนรัน (ไม่อยู่ใน git)
```

## รัน test

```powershell
.\venv\Scripts\python.exe manage.py test meters
```

test ทุกตัว mock ฐานข้อมูล SQL Server ไว้ จึงรันได้บนเครื่องที่ไม่มี DB/LDAP

## ค่าใน .env สำหรับ Production

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `DJANGO_HTTPS` | `False` | `True` เมื่อเปิดใช้ผ่าน HTTPS -- cookie session/CSRF ส่งเฉพาะ HTTPS และเปิด HSTS (ถ้าตั้งบนเครื่องที่ยังเป็น HTTP จะล็อกอินไม่ได้) |
| `DJANGO_HSTS_SECONDS` | `3600` | อายุ HSTS เมื่อ `DJANGO_HTTPS=True` |
| `DJANGO_BEHIND_PROXY` | `False` | `True` เมื่อ IIS/Nginx รับ HTTPS แล้วส่งต่อเป็น HTTP -- proxy ต้องตั้ง `X-Forwarded-Proto` เองเสมอ |
| `DJANGO_LOG_DIR` | `var/logs` | โฟลเดอร์ไฟล์ log (`cms.log` หมุนวันละไฟล์ เก็บ 30 วัน) |
| `DJANGO_LOG_LEVEL` | `INFO` | ระดับ log ของแอป `meters` |
| `DJANGO_CACHE_DIR` | `var/cache` | cache แบบไฟล์ ใช้นับการล็อกอินผิด (ทุก worker บนเครื่องเดียวกันเห็นร่วมกัน) |
| `CMS_ACCESS_REFRESH_SECONDS` | `600` | ดึงสิทธิ์จาก K2 ใหม่ทุกกี่วินาทีระหว่างล็อกอินค้าง (`0` = ไม่ดึงใหม่) |

## ปิดปรับปรุงระบบ (หน้า 503)

ระหว่างปรับปรุง ทุกหน้าจะแสดง "ปิดปรับปรุงระบบชั่วคราว" (HTTP 503) เปิด/ปิดได้ทันทีโดยไม่ต้อง restart เว็บ:

```powershell
.\venv\Scripts\python.exe manage.py maintenance on --message "ปรับปรุงฐานข้อมูล" --until "23 พ.ย. 2569 18:00 น."
.\venv\Scripts\python.exe manage.py maintenance status
.\venv\Scripts\python.exe manage.py maintenance off
```

คำสั่ง `on` สร้างไฟล์ `var/maintenance.json` ส่วน `off` ลบไฟล์นั้น หน้า 503 ไม่แตะฐานข้อมูลใดๆ
จึงแสดงได้แม้ SQL Server/SQLite ใช้งานไม่ได้

**ผู้ดูแลยังเห็นหน้าเว็บจริงระหว่างปรับปรุง** (เพื่อตรวจสิ่งที่แก้ก่อนเปิดระบบ) ได้ 3 ทาง:
1. **ลิงก์ผ่าน** -- คำสั่ง `on` และ `status` พิมพ์ลิงก์ `...?maintenance_bypass=<รหัส>` ให้
   เปิดครั้งเดียว เบราว์เซอร์นั้นจะใช้ระบบได้ทุกหน้า (ไม่ขึ้นกับ IP ใช้ได้แม้อยู่หลัง IIS/proxy)
   รหัสสุ่มใหม่ทุกครั้งที่สั่ง `on` -- ห้ามส่งลิงก์ให้ผู้ใช้ทั่วไป
2. **เปิดจากเครื่องเซิร์ฟเวอร์เอง** (`localhost` / `127.0.0.1`) ผ่านได้เสมอ
3. **IP ใน `CMS_MAINTENANCE_ALLOW_IPS`**

ระหว่างที่ผู้ดูแลเห็นหน้าเว็บจริง จะมีแถบสีส้มด้านบนเตือนว่าผู้ใช้ทั่วไปยังเห็นหน้า 503 อยู่

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `CMS_MAINTENANCE_ALLOW_IPS` | (ว่าง) | IP ที่ยังเข้าระบบได้ระหว่างปรับปรุง คั่นด้วย `,` (localhost ผ่านเสมอ ไม่ต้องใส่) |
| `CMS_MAINTENANCE_BYPASS_TOKEN` | (ว่าง) | รหัสลิงก์ผ่านเมื่อเปิดโหมดจาก `.env` (เปิดด้วยคำสั่ง `on` ไม่ต้องตั้ง ระบบสุ่มให้) |
| `CMS_MAINTENANCE_MODE` | `False` | บังคับเปิดโหมดปรับปรุงจาก `.env` (ต้อง restart) |
| `CMS_MAINTENANCE_MESSAGE` / `CMS_MAINTENANCE_UNTIL` | (ว่าง) | ข้อความ/เวลาเริ่มต้น เมื่อไม่ได้ระบุในคำสั่ง `on` |
| `CMS_MAINTENANCE_RETRY_AFTER` | `3600` | ค่า header `Retry-After` (วินาที) |
| `CMS_MAINTENANCE_FLAG_FILE` | `var/maintenance.json` | ที่อยู่ไฟล์ธง -- ถ้ารันหลายเครื่องให้ชี้ไปที่ที่ทุกเครื่องเห็นร่วมกัน |

ล็อกอินผิด 5 ครั้งต่อบัญชี หรือ 30 ครั้งต่อ IP จะถูกพัก 15 นาที (ค่าอยู่ใน `meters/views/auth.py`)

## วิธีติดตั้งและรัน

```bash
# 1) สร้าง virtual environment (แนะนำ)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2) ติดตั้ง dependencies
pip install -r requirements.txt

# 3) ตั้งค่า .env
cp .env.example .env
# แล้วแก้ค่า DB_NAME / DB_USER / DB_PASSWORD / DB_HOST ให้ตรงกับ SQL Server จริง

# 4) รันเซิร์ฟเวอร์
python manage.py runserver
```

จากนั้นเปิดเบราว์เซอร์ไปที่ `http://127.0.0.1:8080/` แล้วอัปโหลดไฟล์ Excel ได้เลย

### เปลี่ยน port ของเว็บ

Django ปกติใช้ port 8000 ตายตัวและไม่มีไฟล์ setting ให้แก้ โปรเจกต์นี้จึงดักไว้ที่ `manage.py`
ให้อ่านค่าจาก `.env` ได้ (ค่าเริ่มต้น 8080):

```
RUNSERVER_PORT=8080
```

แก้ค่านี้ใน `.env` แล้ว `python manage.py runserver` จะขึ้น port ใหม่ให้เอง
ถ้าอยากใช้ port อื่นชั่วคราวโดยไม่แก้ไฟล์ ระบุต่อท้ายคำสั่งได้ตามปกติ เช่น
`python manage.py runserver 9000` หรือ `python manage.py runserver 0.0.0.0:9000`
(ค่าที่พิมพ์ต่อท้ายจะชนะค่าใน `.env` เสมอ)

หมายเหตุ: `RUNSERVER_PORT` ใช้กับ dev server เท่านั้น ไม่เกี่ยวกับ `DB_PORT`
ซึ่งเป็น port ของ SQL Server (1433)

## ข้อกำหนดก่อนใช้งานจริง

1. ต้องรัน `Contract_Meter_Setup.sql` และ `Contract_Termination_Setup.sql` บนฐานข้อมูลปลายทางก่อน
   (สร้างตาราง `Contract_meter_ms`, `Contract_meter_tr` ให้ครบ)
2. เครื่องที่รัน Django ต้องติดตั้ง **ODBC Driver 17 (หรือ 18) for SQL Server** ของ Microsoft ไว้ก่อน
   ไม่งั้น `mssql-django` จะต่อฐานข้อมูลไม่ได้
3. คอลัมน์ Excel จับคู่ด้วยชื่อหัวคอลัมน์ (`COL_KEYS` ใน `meters/services/excel_import.py`)
   ไม่ใช่ตำแหน่ง -- ถ้าชื่อหัวคอลัมน์ในไฟล์เปลี่ยน ต้องแก้คำค้นในนี้ด้วย
4. ระบบล็อกอินตรวจรหัสผ่านกับ Buasri LDAP จากนั้นแปลง `BUASRI_ID` เป็น
   `PERSON_ID` ผ่าน `[EMPLOYEE].[SAP_FI].[dbo].[v_sarabun_ess_Person]` แล้วอ่านสิทธิ์
   จาก `SysUserGroupAssiciate` และ `SysGroup` ในฐานเดิม รหัสผ่านจะไม่ถูกบันทึกลงระบบนี้
5. ตั้งค่า `LDAP_SERVER_URI` และ `LDAP_USER_DN_TEMPLATE` ใน `.env` ก่อนใช้งาน
   ตัวเลือกเพิ่มเติมคือ `LDAP_CONNECT_TIMEOUT`, `LDAP_START_TLS` และ `LDAP_TLS_VALIDATE`
