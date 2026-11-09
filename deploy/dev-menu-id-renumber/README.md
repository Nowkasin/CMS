# ย้ายเลขเมนู DEV จาก 90/83–89 เป็น 83/84–90

ไฟล์นี้ใช้เฉพาะฐาน DEV ปัจจุบันที่มี mapping ดังนี้:

| เดิม | ใหม่ | key |
|---:|---:|---|
| 90 | 83 | `water_electric_new` |
| 83 | 84 | `meter_management` |
| 84 | 85 | `excel_upload` |
| 85 | 86 | `excel_download` |
| 86 | 87 | `phase_management` |
| 87 | 88 | `dashboard_view` |
| 88 | 89 | `contract_termination` |
| 89 | 90 | `activity_log_view` |

`renumber_menu_ids.sql` มีค่าเริ่มต้น `@Mode = N'PREVIEW'` จึงอ่านและแสดง
mapping เท่านั้น หากตรวจผลแล้วจึงเปลี่ยนเป็น `N'APPLY'` เพื่อย้ายจริง หรือ
`N'ROLLBACK'` เพื่อคืนเลขเดิม

ก่อน `APPLY` ต้อง:

1. สำรองฐาน `SWU_contract`
2. บันทึกหรือยกเลิกและปิดหน้ากำหนดสิทธิ์ K2 ทุกหน้าต่าง
3. หยุดการแก้สิทธิ์ชั่วคราวระหว่างรัน
4. ปรับเงื่อนไขซ่อนใน `SP_2001_GetSystemMenu` หลังย้ายเป็น
   `ParentMenu = 83 AND MenuId IN (84, 85, 86, 87, 88, 89, 90)`
5. ออกจากระบบแล้วเข้าสู่ระบบ K2 และ Django ใหม่

ห้ามใช้ไฟล์นี้บน PRD เพราะเลขเมนูของ PRD ไม่จำเป็นต้องตรงกับ DEV

