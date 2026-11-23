"""ตัวช่วยประกอบ SQL ที่ใช้ร่วมกันหลาย service (ไม่มีการเชื่อมต่อฐานข้อมูลในไฟล์นี้)"""


def _to_sql_like_pattern(search):
    """
    แปลงคำค้นแบบที่คนคุ้นเคย (Excel/Windows) เป็น SQL LIKE pattern:
      ?  -> ตัวอักษรใดก็ได้ 1 ตัว   (SQL: _)
      *  -> ตัวอักษรใดก็ได้ 0 ตัวขึ้นไป (SQL: %)
    ต้อง escape % และ _ ตัวจริงที่ผู้ใช้พิมพ์มาก่อน ไม่งั้นถ้าเลขสัญญามี % หรือ _ อยู่จริง
    จะถูกตีความเป็น wildcard ของ SQL ไปโดยไม่ตั้งใจ
    """
    escaped = search.replace('[', '[[]').replace('%', '[%]').replace('_', '[_]')
    escaped = escaped.replace('?', '_').replace('*', '%')
    return f"%{escaped}%"


# ชื่อสาธารณะ -- ชื่อเดิมที่ขึ้นต้นด้วย _ ยังคงไว้ให้โค้ดเดิมที่ import อยู่ใช้ได้
to_sql_like_pattern = _to_sql_like_pattern
