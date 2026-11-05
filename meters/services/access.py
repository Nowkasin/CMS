"""อ่านตัวตนบุคลากรและสิทธิ์จากระบบ K2 เดิมโดยไม่แก้ไขข้อมูล"""

from .db import get_db_connection


CMS_PARENT_MENU_ID = 41


def fetch_user_access(buasri_id):
    """แปลง Buasri ID เป็น PERSON_ID แล้วคืนกลุ่มและเมนู CMS ที่เปิดใช้งาน

    คืน None เมื่อไม่พบ Buasri ID ในข้อมูลบุคลากร และคืน dict ที่ groups เป็น []
    เมื่อพบบุคลากรแต่ยังไม่มีกลุ่มที่เปิดใช้งานในระบบ K2 เดิม

    การอ่านเมนูใช้ความสัมพันธ์เดิมของ K2 เท่านั้น:
    SysUserGroupAssiciate -> SysMenuGroupAssociate -> Sysmenu
    โดย menuId 41 คือเมนูหลัก "ค่าน้ำประปา-ค่าไฟฟ้า"
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # View อยู่ที่ Linked Server EMPLOYEE ฐาน SAP_FI ระบบนี้อ่านอย่างเดียว
        # DISTINCT กันกรณี View บุคลากรคืนข้อมูลบุคคลเดียวกันมากกว่าหนึ่งแถว
        cursor.execute(
            """
            SELECT DISTINCT
                person.PERSON_ID,
                person.FOA_TH,
                person.PERSON_FNAME_TH,
                person.PERSON_LNAME_TH
            FROM [EMPLOYEE].[SAP_FI].[dbo].[v_sarabun_ess_Person] AS person
            WHERE person.BUASRI_ID COLLATE SQL_Latin1_General_CP1_CI_AS = ?
            """,
            buasri_id,
        )
        person_rows = cursor.fetchall()
        if not person_rows:
            return None

        person_ids = {
            str(row[0]).strip() for row in person_rows if row[0] is not None
        }
        if len(person_ids) != 1:
            raise ValueError('Buasri ID maps to more than one PERSON_ID')

        person_id = person_ids.pop()
        person_row = person_rows[0]
        title = str(person_row[1] or '').strip()
        first_name = str(person_row[2] or '').strip()
        last_name = str(person_row[3] or '').strip()
        display_name = ' '.join(
            part for part in (f'{title}{first_name}', last_name) if part
        )
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

        cursor.execute(
            """
            SELECT DISTINCT
                menu.menuId,
                menu.menu_name_eng,
                menu.MenuNameThai,
                menu.MenuUrl,
                menu.OrderNo,
                menu.ParentMenu
            FROM dbo.SysUserGroupAssiciate AS ug
            INNER JOIN dbo.SysGroup AS g
                ON g.GroupId = ug.GroupId
            INNER JOIN dbo.SysMenuGroupAssociate AS menu_group
                ON menu_group.GroupId = ug.GroupId
            INNER JOIN dbo.Sysmenu AS menu
                ON menu.menuId = menu_group.MenuId
            WHERE ug.Person_Id = ?
              AND ug.IsActive = 1
              AND g.IsActive = 1
              AND menu_group.IsActive = 1
              AND menu.IsActive = 1
              AND (
                    menu.menuId = ?
                    OR menu.ParentMenu = ?
              )
            ORDER BY menu.OrderNo, menu.menuId
            """,
            person_id,
            CMS_PARENT_MENU_ID,
            CMS_PARENT_MENU_ID,
        )
        menu_rows = cursor.fetchall()
        menus = [
            {
                'id': row[0],
                'key': str(row[1] or '').strip(),
                'name': str(row[2] or '').strip(),
                'url': str(row[3] or '').strip(),
                'order': row[4],
            }
            for row in menu_rows
            if row[5] == CMS_PARENT_MENU_ID
        ]
        permissions = {
            menu['key']: True for menu in menus if menu['key']
        }
        return {
            'person_id': person_id,
            'display_name': display_name or buasri_id,
            'groups': groups,
            'has_cms_access': any(
                row[0] == CMS_PARENT_MENU_ID for row in menu_rows
            ),
            'menus': menus,
            'menu_ids': [menu['id'] for menu in menus],
            'permissions': permissions,
        }
    finally:
        conn.close()
