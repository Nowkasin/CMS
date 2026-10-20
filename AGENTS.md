# AGENTS.md

เอกสารนี้เป็นแนวทางสำหรับผู้ช่วยเขียนโค้ดและผู้พัฒนาที่ทำงานในโปรเจกต์ CMS นี้ ให้แก้ไขระบบอย่างสม่ำเสมอและไม่กระทบฐานข้อมูลเดิมโดยไม่ตั้งใจ

## ภาพรวมระบบ

- ระบบเป็น Django 6 สำหรับจัดการมิเตอร์น้ำ–ไฟ ข้อมูลสัญญา การนำเข้า Excel และการยกเลิกสัญญา
- โค้ดหลักอยู่ในแอป `meters`
- URL อยู่ที่ `meters/urls.py`
- View แยกตามงานอยู่ใน `meters/views/`
- การเข้าถึงข้อมูลธุรกิจอยู่ใน `meters/services/`
- Template อยู่ใน `templates/meters/`
- Static files อยู่ใน `static/meters/`

## ฐานข้อมูล

- ข้อมูลธุรกิจจริง เช่น สัญญา มิเตอร์ พื้นที่ กลุ่มผู้ใช้ และประวัติการทำงาน อยู่ใน SQL Server เดิม
- การเชื่อมต่อ SQL Server ต้องทำผ่าน `meters/services/` และ `pyodbc`
- ห้ามสร้าง แก้ไข หรือลบ Table, View, Stored Procedure, Column, Index หรือข้อมูลใน SQL Server เว้นแต่ผู้ใช้สั่งอย่างชัดเจน
- ห้ามสร้าง Django migration สำหรับตารางธุรกิจเดิม
- ถ้าจำเป็นต้องเขียนข้อมูลธุรกิจ ให้ใช้ Service หรือ Stored Procedure เดิม และใช้ Transaction ตามรูปแบบที่มีอยู่
- ใช้ Query แบบ Parameterized เสมอ ห้ามประกอบ SQL ด้วยค่าจากผู้ใช้
- `db.sqlite3` ใช้สำหรับกลไกภายในของ Django เช่น `auth_user` และ `django_session` เท่านั้น ไม่ใช่ฐานข้อมูลธุรกิจ
- ห้ามลบหรือ Reset `db.sqlite3` โดยไม่ได้รับคำสั่งชัดเจน

## Authentication และสิทธิ์

- ตรวจรหัสผ่านด้วย Buasri LDAP ผ่าน `meters/auth_backend.py`
- ห้ามบันทึกหรือ Log รหัสผ่าน LDAP
- หลัง LDAP ผ่าน ระบบแปลง Buasri ID เป็น `PERSON_ID` ผ่าน `v_sarabun_ess_Person`
- สิทธิ์เข้า CMS อ่านจาก `SysUserGroupAssiciate` และ `SysGroup` ผ่าน `meters/services/access.py`
- การตรวจสิทธิ์จาก SQL Server เป็นการอ่านข้อมูล ห้ามสร้างหรือแก้ไขกลุ่มผู้ใช้จาก Django โดยไม่ได้รับคำสั่ง
- หน้าเว็บทั้งหมดต้องผ่านการล็อกอิน ยกเว้น View ที่ตั้งใจใช้ `@login_not_required`
- อย่าแสดงรายละเอียด Connection String, Password, Secret Key หรือข้อมูลจาก `.env` ในหน้าเว็บหรือ Log

## โครงสร้างโค้ด

- View ทำหน้าที่รับ Request, ตรวจ Input, เรียก Service และส่ง Context ให้ Template
- SQL และกฎที่เกี่ยวข้องกับฐานข้อมูลต้องอยู่ใน `meters/services/` ไม่เขียน SQL ตรงใน View หรือ Template
- Validation ของ Form และไฟล์อัปโหลดให้อยู่ใน `meters/forms.py` หรือ Service ที่เกี่ยวข้อง
- หลีกเลี่ยงการสร้างไฟล์ขนาดใหญ่รวมหลายหน้าที่รับผิดชอบ ให้แยกตาม Feature ตามโครงสร้างปัจจุบัน
- รักษาชื่อ URL, Form field, Session key และ DOM ID ที่ JavaScript ใช้อยู่ เว้นแต่แก้ทุกจุดที่อ้างอิงพร้อมกัน
- เพิ่ม Comment เมื่ออธิบายข้อจำกัดของข้อมูลเดิมหรือเหตุผลที่มองจากโค้ดไม่ออก หลีกเลี่ยง Comment ที่เพียงทวนคำสั่งในโค้ด

## Template และรูปแบบหน้าจอ

- หน้าภายในระบบต้อง `{% extends "meters/base.html" %}`
- หน้าล็อกอินเป็นหน้า Standalone และไม่ต้องแสดง Top Nav หรือ Sidebar
- Top Nav อยู่ที่ `templates/meters/partials/top_nav.html`
- Sidebar อยู่ที่ `templates/meters/partials/sidebar.html`
- เมนูหลักอยู่ใน Sidebar ส่วนชื่อระบบ ชื่อผู้ใช้ และปุ่มออกจากระบบอยู่ใน Top Nav
- ลิงก์เมนูเปิดในแท็บเดิม ห้ามเพิ่ม `target="_blank"` โดยไม่มีเหตุผลจากผู้ใช้
- ใช้สี `brand` ที่กำหนดใน `base.html` เป็นสีหลัก
- ใช้ฟอนต์ Prompt จาก `static/meters/webfonts/` และไม่เพิ่มบริการฟอนต์ภายนอก
- หัวหน้าควรมี Breadcrumb, `h1` และคำอธิบายสั้นในรูปแบบเดียวกับ `meter_list.html` และ `upload.html`
- Card ใช้พื้นหลังขาว เส้นขอบสีเทา มุมโค้ง และเงาอ่อนให้สม่ำเสมอ
- ตารางที่กว้างต้องมี `overflow-x-auto` และกำหนดความกว้างขั้นต่ำให้คอลัมน์อ่านได้
- คอลัมน์ที่มีปุ่ม เช่น แก้ไขหรือดูรายละเอียด ใช้หัวคอลัมน์ `ดำเนินการ` และจัดตรงกับปุ่มในแถว
- Stepper ใช้ `templates/meters/stepper.html` และต้องแสดงครบโดยไม่มี Scrollbar
- ออกแบบ Responsive เสมอ บนจอเล็ก Form และปุ่มต้องเรียงลงมาโดยไม่ล้นหน้าจอ
- อย่าเปลี่ยนข้อความทางธุรกิจหรือความหมายของสถานะเพื่อความสวยงามเพียงอย่างเดียว

## การอัปโหลด Excel

- รองรับเฉพาะนามสกุลที่กำหนดใน `meters/forms.py`
- ต้องตรวจนามสกุล ขนาด เนื้อหาไฟล์ และจำนวนแถวก่อน Parse
- ห้ามเชื่อถือชื่อไฟล์หรือนามสกุลเพียงอย่างเดียว
- ข้อมูลจาก Step 1–3 เก็บเป็น Staged data ใน Session และยังไม่ถือว่าบันทึกจริงจนกว่าผู้ใช้ยืนยัน
- ห้ามเปลี่ยน Flow ของ `step1`, `step2`, `step3`, `step4` หรือ `restart` โดยไม่ตรวจผลต่อ Session ทั้งกระบวนการ

## JavaScript และ Static files

- JavaScript เฉพาะหน้าอยู่ใน `static/meters/js/`
- หลีกเลี่ยง Inline JavaScript ใหม่ ถ้าพฤติกรรมมีหลายขั้นตอนหรือใช้ซ้ำได้
- ก่อนเปลี่ยน ID หรือ Class ให้ค้นหาการอ้างอิงใน JavaScript ก่อนเสมอ
- รูปภาพอยู่ใน `static/meters/images/`
- ฟอนต์ Prompt อยู่ใน `static/meters/webfonts/`

## การตรวจสอบก่อนส่งงาน

ใช้ Python จาก Virtual Environment ของโปรเจกต์:

```powershell
.\venv\Scripts\python.exe manage.py check
```

ตรวจปัญหา Whitespace:

```powershell
git diff --check
```

เมื่อแก้ Template ให้ตรวจว่า Template Compile ได้ และ Render หน้าที่เกี่ยวข้องเมื่อมี Context พร้อมใช้งาน

เมื่อแก้ Logic การนำเข้า การบันทึก หรือ Query ให้ทดสอบกรณีสำเร็จ ข้อมูลว่าง ข้อมูลผิดรูปแบบ และ Database error ที่เกี่ยวข้อง ห้ามใช้ Production data เพื่อทดลองเขียนข้อมูล

## ขอบเขตการแก้ไข

- รักษาการเปลี่ยนแปลงให้อยู่ในขอบเขตที่ผู้ใช้ขอ
- ห้ามเปลี่ยน `.env`, Secret, Credential หรือค่าการเชื่อมต่อจริงโดยไม่รับคำสั่ง
- ห้ามลบข้อมูล ล้างฐานข้อมูล หรือรันคำสั่งที่เปลี่ยน Schema โดยไม่รับคำสั่งชัดเจน
- ถ้างานเกี่ยวข้องกับฐานข้อมูลแต่ผู้ใช้ขอ “แก้เฉพาะโค้ด” ให้แก้ไฟล์โค้ดเท่านั้น และใช้การตรวจสอบที่ไม่เขียนข้อมูล
- ถ้าพบความไม่แน่นอนเกี่ยวกับชื่อ Table, Column, Stored Procedure หรือกฎธุรกิจ ให้ตรวจจากโค้ดและ Schema แบบอ่านอย่างเดียวก่อน ห้ามเดาแล้วเขียนข้อมูล
