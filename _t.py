import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from meters import services
from meters.services.db import get_db_connection

conn = get_db_connection(); cur = conn.cursor()

print('=' * 78)
print('1) sp_Contract_Meter_BindToContract กันผูกซ้ำไหม')
print('=' * 78)
cur.execute("SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.sp_Contract_Meter_BindToContract'))")
sp = cur.fetchone()[0]
for line in sp.splitlines():
    s = line.strip()
    if any(k in s.upper() for k in ('NOT EXISTS', 'EXISTS', 'MERGE', 'IF ', 'INSERT', 'UPDATE', 'WHERE')):
        print('  ', s[:120])

print('\n' + '=' * 78)
print('2) find_existing_meter คืนตัวไหน เมื่อข้อมูลมีคู่แฝด')
print('=' * 78)
cur.execute("""SELECT SubArea_id, Meter_type_cd, MIN(Meter_id), MAX(Meter_id), MAX(Meter_no)
               FROM Contract_meter_ms WHERE UseOrNot=1
               GROUP BY SubArea_id, Meter_type_cd HAVING COUNT(*)>1
               ORDER BY SubArea_id, Meter_type_cd""")
dups = [tuple(r) for r in cur.fetchall()]
same = 0
for sa, tcd, lo, hi, no in dups[:6]:
    got = services.find_existing_meter(cur, sa, tcd, no)
    t = 'น้ำ' if tcd == 9 else 'ไฟ'
    mark = 'คืนตัวเก่าสุด' if got and got[0] == lo else 'คืนตัวอื่น!'
    print(f'   {sa:6s} {t} คู่ [{lo}, {hi}] -> find_existing_meter คืน {got[0] if got else None}  {mark}')
for sa, tcd, lo, hi, no in dups:
    got = services.find_existing_meter(cur, sa, tcd, no)
    if got and got[0] == lo:
        same += 1
print(f'   ทั้ง {len(dups)} กลุ่ม: คืนตัวเก่าสุด {same} กลุ่ม (คงที่ ไม่สุ่ม)')

print('\n' + '=' * 78)
print('3) อัปโหลดข้อมูลเดิมซ้ำตอนนี้ จะงอกมิเตอร์เพิ่มไหม (ROLLBACK)')
print('=' * 78)
cur.execute("SELECT COUNT(*) FROM Contract_meter_ms"); ms0 = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM Contract_meter_tr"); tr0 = cur.fetchone()[0]
print(f'   ก่อน: meter_ms {ms0} / meter_tr {tr0}')

# สร้างแถวแบบที่ parse_excel_staged ปั้นออกมา จากข้อมูลที่มีอยู่จริง
cur.execute("""SELECT TOP 6 mt.Contract_id, m.Location_id, m.Area_id, m.SubArea_id,
                      m.Meter_type_cd, m.Meter_no, m.Phase_type
               FROM Contract_meter_tr mt
               JOIN Contract_meter_ms m ON m.Meter_id = mt.Meter_id
               WHERE mt.UseOrNot = 1 AND m.UseOrNot = 1 AND m.Meter_no IS NOT NULL
               ORDER BY mt.Contract_id, m.Meter_type_cd""")
rows = []
for r in cur.fetchall():
    rows.append({
        'row_no': len(rows) + 1,
        'db_contract_id': int(r[0]), 'contract_code': None,
        'location_id': r[1], 'area_id': r[2], 'subarea_id': r[3],
        'type_cd': int(r[4]), 'meter_no': r[5], 'phase_type': r[6],
        'final_status': 'ok', 'message': '',
    })
print(f'   จำลองอัปโหลดซ้ำ {len(rows)} แถว:',
      [(x['subarea_id'], x['type_cd'], x['meter_no']) for x in rows])

created = 0
reused = 0
for r in rows:
    existing = services.find_existing_meter(cur, r['subarea_id'], r['type_cd'], r['meter_no'])
    if existing:
        reused += 1
    else:
        created += 1
print(f'   -> ใช้ทะเบียนเดิม {reused} แถว / จะสร้างใหม่ {created} แถว')

# เรียก sp_meter_save แบบเดียวกับ commit_staged_rows เพื่อดูว่า INSERT เพิ่มจริงไหม
logs = []
for r in rows:
    existing = services.find_existing_meter(cur, r['subarea_id'], r['type_cd'], r['meter_no'])
    mid = services.sp_meter_save(
        cur, r['location_id'], r['area_id'], r['subarea_id'], r['type_cd'],
        r['meter_no'], 'ปกติ', 'test', logs,
        phase_type=r['phase_type'], meter_id=existing[0] if existing else None,
    )
    if r['db_contract_id']:
        services.sp_bind_to_contract(cur, r['db_contract_id'], r['location_id'], r['area_id'],
                                     r['subarea_id'], mid, 'test', logs)

cur.execute("SELECT COUNT(*) FROM Contract_meter_ms"); ms1 = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM Contract_meter_tr"); tr1 = cur.fetchone()[0]
print(f'   หลัง: meter_ms {ms1} (+{ms1-ms0}) / meter_tr {tr1} (+{tr1-tr0})')
print('   ->', 'ไม่งอกเพิ่ม ตัวกันซ้ำทำงาน' if (ms1 == ms0 and tr1 == tr0)
      else f'ยังงอกเพิ่ม! ms +{ms1-ms0} tr +{tr1-tr0}')

conn.rollback()
cur.execute("SELECT COUNT(*) FROM Contract_meter_ms"); print('\n   หลัง rollback: meter_ms', cur.fetchone()[0])

print('\n' + '=' * 78)
print('4) ถ้าจะล้างคู่แฝด: ตัวไหนมีข้อมูลผูกอยู่บ้าง (ตัดสินว่าเก็บตัวไหน)')
print('=' * 78)
cur.execute("""
WITH dup AS (
    SELECT Meter_id, SubArea_id, Meter_type_cd, Meter_no,
           ROW_NUMBER() OVER (PARTITION BY SubArea_id, Meter_type_cd ORDER BY Meter_id) AS rn,
           COUNT(*) OVER (PARTITION BY SubArea_id, Meter_type_cd) AS n
    FROM Contract_meter_ms WHERE UseOrNot = 1
)
SELECT d.SubArea_id, d.Meter_type_cd, d.Meter_id, d.rn, d.Meter_no,
       (SELECT COUNT(*) FROM Contract_meter_reading_tr r WHERE r.Meter_id = d.Meter_id) AS readings,
       (SELECT COUNT(*) FROM Contract_meter_tr t WHERE t.Meter_id = d.Meter_id) AS binds
FROM dup d WHERE d.n > 1
ORDER BY d.SubArea_id, d.Meter_type_cd, d.rn""")
keep_readings = extra_readings = 0
for r in cur.fetchall():
    t = 'น้ำ' if r[1] == 9 else 'ไฟ'
    role = 'เก็บ ' if r[3] == 1 else 'ซ้ำ  '
    flag = '  <-- มีเลขอ่าน!' if r[5] else ''
    if r[5]:
        if r[3] == 1:
            keep_readings += r[5]
        else:
            extra_readings += r[5]
    print(f'   {role}{r[0]:6s} {t} Meter_id {r[2]:5d} (ลำดับ {r[3]}) เลข {r[4]:12s} '
          f'เลขอ่าน {r[5]} ผูกสัญญา {r[6]}{flag}')
print(f'\n   เลขอ่านที่อยู่กับตัวที่จะเก็บ {keep_readings} แถว / อยู่กับตัวซ้ำ {extra_readings} แถว')
conn.close()
