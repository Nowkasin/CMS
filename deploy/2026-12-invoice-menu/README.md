# ติดตั้งเมนู "ใบแจ้งหนี้"

เพิ่มเมนูย่อย key `invoice_print` (หน้า `/invoice/`) ใต้ระบบ `water_electric_new`
และให้สิทธิ์ 2 กลุ่ม ไม่สร้างหรือแก้ Schema

- **Cashier ID Approve ส่วนการคลัง** (`5C8F2016-ED3C-4E31-8633-CD8984FD7DCB`) ผู้ใช้งานหลัก
- **ผู้ดูแลระบบ ( Admin )** (`9B148353-6383-40D7-B3B8-F04FC8C5A4C5`) ดูแลและทดสอบเมนู

หน้าใบแจ้งหนี้อ่านข้อมูลอย่างเดียว ผ่าน view `v_contract_price_tr` และ
SP เดิม `sp_6000_Contact_Doc_invoice` (ตัวเดียวกับที่ฟอร์ม K2 FRM_4019_Invoice_CMS ใช้)

## ไฟล์

1. `01_apply_invoice_menu.sql` — เพิ่ม/ปรับเมนู และให้สิทธิ์กลุ่มภายใน Transaction
2. `02_rollback_invoice_menu.sql` — ปิดเมนูและสิทธิ์ของเมนูนี้ โดยไม่ลบแถว

## ลำดับติดตั้ง

1. ต้องติดตั้งชุด `deploy/2026-11-cms-menu` แล้ว (มีเมนูหลัก `water_electric_new`)
2. แก้ `@CmsBaseUrl` ใน `01_apply_invoice_menu.sql` ให้ตรงกับ URL จริง
3. ถ้ากลุ่มอื่นต้องใช้ด้วย เพิ่ม `GroupId` ในตาราง `@Groups`
4. Deploy โค้ดรุ่นที่มีหน้า `/invoice/` แล้วรัน `collectstatic`
5. รัน `01_apply_invoice_menu.sql`
6. ผู้ใช้ในกลุ่มจะเห็นเมนูภายใน 10 นาที (CMS ดึงสิทธิ์ใหม่ทุก `CMS_ACCESS_REFRESH_SECONDS`)
   หรือออกจากระบบแล้วเข้าใหม่
