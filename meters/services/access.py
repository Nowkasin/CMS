"""อ่านตัวตนบุคลากรและสิทธิ์จากระบบ K2 เดิมโดยไม่แก้ไขข้อมูล"""

from .db import get_db_connection


def fetch_user_access(buasri_id):
    """แปลง Buasri ID เป็น PERSON_ID แล้วคืนกลุ่มที่เปิดใช้งาน

    คืน None เมื่อไม่พบ Buasri ID ในข้อมูลบุคลากร และคืน dict ที่ groups เป็น []
    เมื่อพบบุคลากรแต่ยังไม่มีกลุ่มที่เปิดใช้งานในระบบ K2 เดิม
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # View อยู่ที่ Linked Server EMPLOYEE ฐาน SAP_FI ระบบนี้อ่านอย่างเดียว
        # DISTINCT กันกรณี View บุคลากรคืนข้อมูลบุคคลเดียวกันมากกว่าหนึ่งแถว
        cursor.execute(
            """
            SELECT DISTINCT person.PERSON_ID
            FROM [EMPLOYEE].[SAP_FI].[dbo].[v_sarabun_ess_Person] AS person
            WHERE person.BUASRI_ID COLLATE SQL_Latin1_General_CP1_CI_AS = ?
            """,
            buasri_id,
        )
        person_rows = cursor.fetchmany(2)
        if not person_rows:
            return None
        if len(person_rows) > 1:
            raise ValueError('Buasri ID maps to more than one PERSON_ID')

        person_id = str(person_rows[0][0]).strip()
        cursor.execute(
            """
            SELECT DISTINCT
                CONVERT(nvarchar(36), g.GroupId) AS GroupId,
                g.GroupName
            FROM dbo.SysUserGroupAssiciate AS ug
            INNER JOIN dbo.SysGroup AS g ON g.GroupId = ug.GroupId
            WHERE ug.Person_Id = ?
              AND ug.IsActive = 1
              AND g.IsActive = 1
            ORDER BY g.GroupName
            """,
            person_id,
        )
        groups = [
            {'id': row[0], 'name': row[1]} for row in cursor.fetchall()
        ]
        return {'person_id': person_id, 'groups': groups}
    finally:
        conn.close()
