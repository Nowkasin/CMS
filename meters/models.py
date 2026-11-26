# meters/models.py
#
# ตั้งใจว่างไว้ -- ระบบนี้ไม่ใช้ Django ORM กับข้อมูลธุรกิจ
# ตารางสัญญา/มิเตอร์/พื้นที่อยู่ใน SQL Server เดิม และอ่าน/เขียนผ่าน pyodbc ใน meters/services/
# (ดู AGENTS.md หัวข้อ "ฐานข้อมูล") ห้ามสร้าง model/migration สำหรับตารางธุรกิจเดิม
#
# เดิมมี model แบบ managed=False ของ Contract_status_ms / Contract_hrd_tr / Contract_meter_ms /
# Contract_meter_tr ที่ไม่มีโค้ดไหนเรียกใช้ และนิยามคอลัมน์ไม่ครบตาม schema จริง
# ทำให้คนอ่านเข้าใจผิดว่าระบบใช้ ORM จึงเอาออก
