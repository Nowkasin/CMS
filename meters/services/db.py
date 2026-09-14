# meters/services/db.py
"""
เชื่อมต่อ SQL Server ธุรกิจจริงผ่าน pyodbc -- ทุกโมดูลใน services/ เรียกใช้ get_db_connection()
จากที่นี่ที่เดียว
"""
import pyodbc
from decouple import config


def get_db_connection():
    """
    ต่อ SQL Server ธุรกิจจริงผ่าน pyodbc โดยอ่านค่าเชื่อมต่อจาก .env โดยตรง
    (ไม่ใช่จาก settings.DATABASES['default'] ซึ่งเป็น sqlite ที่ใช้แค่เก็บ session ของ Django เอง)
    ตัวแปรที่ต้องมีใน .env: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_ODBC_DRIVER
    """
    driver = config('DB_ODBC_DRIVER', default='ODBC Driver 17 for SQL Server')
    host = config('DB_HOST')
    port = config('DB_PORT', default='1433')
    name = config('DB_NAME')
    user = config('DB_USER')
    password = config('DB_PASSWORD')

    missing = [k for k, v in {
        'DB_HOST': host, 'DB_NAME': name, 'DB_USER': user, 'DB_PASSWORD': password,
    }.items() if not v]
    if missing:
        raise RuntimeError(
            f"ค่าเชื่อมต่อ SQL Server ขาดหายไปใน .env: {', '.join(missing)} "
            f"กรุณาตรวจสอบไฟล์ .env ที่ root โปรเจกต์"
        )

    # escape ปีกกาใน password กัน connection string พังถ้ารหัสผ่านมี { หรือ } อยู่จริง
    safe_password = str(password).replace('}', '}}')

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={host},{port};"
        f"DATABASE={name};"
        f"UID={user};"
        f"PWD={{{safe_password}}};"
    )
    return pyodbc.connect(conn_str)