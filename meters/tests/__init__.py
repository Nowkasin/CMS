"""
Test อัตโนมัติของ CMS -- รันด้วย  .\\venv\\Scripts\\python.exe manage.py test meters

ทุก test ห้ามต่อ SQL Server จริง: ฟังก์ชันใน meters/services ที่แตะฐานข้อมูลถูก mock
(หรือ mock get_db_connection ด้วย cursor ปลอม) ฐานของ Django เองใช้ SQLite ชั่วคราวที่
test runner สร้างให้ ไม่แตะ db.sqlite3
"""
