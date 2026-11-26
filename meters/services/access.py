"""อ่านตัวตนบุคลากรและสิทธิ์จากระบบ K2 เดิมโดยไม่แก้ไขข้อมูล"""

from .db import get_db_connection


CMS_PARENT_MENU_KEY = 'water_electric_new'


def fetch_user_access(buasri_id):
    """แปลง Buasri ID เป็น PERSON_ID แล้วคืนกลุ่มและเมนู CMS ที่เปิดใช้งาน

    คืน None เมื่อไม่พบ Buasri ID ในข้อมูลบุคลากร และคืน dict ที่ groups เป็น []
    เมื่อพบบุคลากรแต่ยังไม่มีกลุ่มที่เปิดใช้งานในระบบ K2 เดิม

    การอ่านเมนูใช้ความสัมพันธ์เดิมของ K2 เท่านั้น:
    SysUserGroupAssiciate -> SysMenuGroupAssociate -> Sysmenu
    เมนูหลักของระบบใหม่ค้นด้วย key ``water_electric_new`` แทนการผูกกับ
    menuId เพราะเลข Identity ของ Sysmenu อาจต่างกันระหว่าง DEV และ PRD
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
            WITH cms_root AS (
                SELECT menuId
                FROM dbo.Sysmenu
                WHERE menu_name_eng = ?
                  AND IsActive = 1
            )
            SELECT DISTINCT
                menu.menuId,
                menu.menu_name_eng,
                menu.MenuNameThai,
                menu.MenuUrl,
                menu.OrderNo,
                menu.ParentMenu,
                cms_root.menuId AS CmsRootMenuId
            FROM dbo.SysUserGroupAssiciate AS ug
            INNER JOIN dbo.SysGroup AS g
                ON g.GroupId = ug.GroupId
            INNER JOIN dbo.SysMenuGroupAssociate AS menu_group
                ON menu_group.GroupId = ug.GroupId
            INNER JOIN dbo.Sysmenu AS menu
                ON menu.menuId = menu_group.MenuId
            CROSS JOIN cms_root
            WHERE ug.Person_Id = ?
              AND ug.IsActive = 1
              AND g.IsActive = 1
              AND menu_group.IsActive = 1
              AND menu.IsActive = 1
              AND (
                    menu.menuId = cms_root.menuId
                    OR menu.ParentMenu = cms_root.menuId
              )
            ORDER BY menu.OrderNo, menu.menuId
            """,
            CMS_PARENT_MENU_KEY,
            person_id,
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
            if row[5] == row[6]
        ]
        permissions = {
            menu['key']: True for menu in menus if menu['key']
        }
        return {
            'person_id': person_id,
            'display_name': display_name or buasri_id,
            'groups': groups,
            'has_cms_access': any(
                row[0] == row[6] for row in menu_rows
            ),
            'menus': menus,
            'menu_ids': [menu['id'] for menu in menus],
            'permissions': permissions,
        }
    finally:
        conn.close()


# --------------------------------------------------------------------------
# "ดูในมุมมองกลุ่ม" ของผู้ดูแลระบบ -- อ่านอย่างเดียว ใช้ความสัมพันธ์เดิมของ K2
# SysGroup -> SysMenuGroupAssociate -> Sysmenu (เงื่อนไข IsActive เดียวกับ fetch_user_access)
# --------------------------------------------------------------------------
_GROUP_MENU_SQL = """
    WITH cms_root AS (
        SELECT menuId
        FROM dbo.Sysmenu
        WHERE menu_name_eng = ?
          AND IsActive = 1
    )
    SELECT DISTINCT
        CONVERT(nvarchar(36), g.GroupId) AS GroupId,
        g.GroupName,
        menu.menu_name_eng
    FROM dbo.SysGroup AS g
    INNER JOIN dbo.SysMenuGroupAssociate AS menu_group
        ON menu_group.GroupId = g.GroupId
    INNER JOIN dbo.Sysmenu AS menu
        ON menu.menuId = menu_group.MenuId
    CROSS JOIN cms_root
    WHERE g.IsActive = 1
      AND menu_group.IsActive = 1
      AND menu.IsActive = 1
      AND menu.ParentMenu = cms_root.menuId
      {group_filter}
    ORDER BY g.GroupName
"""


def fetch_cms_groups():
    """
    กลุ่ม K2 ที่เปิดใช้งานและได้รับเมนูย่อยของ CMS อย่างน้อยหนึ่งเมนู
    คืน [{'id', 'name', 'permissions': {menu_key: True}}] เรียงตามชื่อกลุ่ม
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(_GROUP_MENU_SQL.format(group_filter=''), CMS_PARENT_MENU_KEY)
        groups = {}
        for group_id, name, key in cursor.fetchall():
            key = str(key or '').strip()
            if not key:
                continue
            group = groups.setdefault(str(group_id).upper(), {
                'id': str(group_id).upper(), 'name': str(name or '').strip(), 'permissions': {},
            })
            group['permissions'][key] = True
        return sorted(groups.values(), key=lambda g: g['name'])
    finally:
        conn.close()


def fetch_group_access(group_id):
    """
    สิทธิ์เมนู CMS ของกลุ่มเดียว -- คืน {'id', 'name', 'permissions'} หรือ None ถ้าไม่พบ/ไม่มีเมนู CMS
    group_id ต้องผ่านการตรวจรูปแบบ GUID จาก view มาก่อน (ส่งเป็นพารามิเตอร์เสมอ)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            _GROUP_MENU_SQL.format(group_filter='AND g.GroupId = CONVERT(uniqueidentifier, ?)'),
            CMS_PARENT_MENU_KEY, group_id,
        )
        rows = cursor.fetchall()
        permissions = {str(key).strip(): True for _, _, key in rows if str(key or '').strip()}
        if not permissions:
            return None
        return {'id': str(rows[0][0]).upper(), 'name': str(rows[0][1] or '').strip(),
                'permissions': permissions}
    finally:
        conn.close()
