# Contract Meter Django

เว็บแอปอัปโหลดไฟล์ Excel สัญญาเช่าพื้นที่ แล้วเรียก stored procedure จริง
(`sp_Contract_Meter_Save`, `sp_Contract_Meter_BindToContract`) บนฐานข้อมูล SQL Server
เพื่อสร้างทะเบียนมิเตอร์น้ำ-ไฟ และผูกกับสัญญา

## โครงสร้างโปรเจกต์

```
contract_meter_django/
├── manage.py
├── requirements.txt
├── .env.example          -- คัดลอกเป็น .env แล้วกรอกค่าจริง
├── config/
│   ├── settings.py       -- อ่านค่าทั้งหมดจาก .env ผ่าน django-environ
│   ├── urls.py
│   └── wsgi.py
├── meters/
│   ├── models.py          -- แมปตารางที่มีอยู่แล้ว (managed=False, ไม่สร้าง/แก้ตารางเอง)
│   ├── services.py        -- เรียก stored procedure ผ่าน raw SQL cursor
│   ├── forms.py            -- ฟอร์มอัปโหลดไฟล์ .xlsx
│   ├── views.py             -- อ่าน Excel + วนแถวเรียก services.py
│   └── urls.py
├── templates/meters/
│   ├── base.html            -- โครง HTML หลัก (ไม่มี CSS ฝังอยู่)
│   └── upload.html          -- หน้าอัปโหลด + แสดงผล log
└── static/meters/css/
    └── style.css             -- CSS ทั้งหมดแยกออกมาไฟล์เดียว
```

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

จากนั้นเปิดเบราว์เซอร์ไปที่ `http://127.0.0.1:8000/` แล้วอัปโหลดไฟล์ Excel ได้เลย

## ข้อกำหนดก่อนใช้งานจริง

1. ต้องรัน `Contract_Meter_Setup.sql` และ `Contract_Termination_Setup.sql` บนฐานข้อมูลปลายทางก่อน
   (สร้างตาราง `Contract_meter_ms`, `Contract_meter_tr` ให้ครบ)
2. เครื่องที่รัน Django ต้องติดตั้ง **ODBC Driver 17 (หรือ 18) for SQL Server** ของ Microsoft ไว้ก่อน
   ไม่งั้น `mssql-django` จะต่อฐานข้อมูลไม่ได้
3. คอลัมน์ Excel ที่ view ใช้อ้างอิง (`meters/views.py` ตัวแปร `COL`) อิงตามไฟล์
   "ข้อมูลสัญญาที่สร้างปี68 ในระบบ CMS" — ถ้าโครงสร้างคอลัมน์ไฟล์เปลี่ยน ต้องแก้ตำแหน่ง index ในนี้ด้วย
4. `DEFAULT_USER = 'web_upload'` ใน `views.py` คือค่าที่บันทึกลง `UserEntry` — เปลี่ยนเป็น username จริงของผู้ใช้ที่ login ได้ถ้าต้องการ (ตอนนี้ยังไม่มีระบบ login)
