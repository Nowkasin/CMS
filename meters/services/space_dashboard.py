"""สรุปพื้นที่จากรอบข้อมูลเดิม โดยไม่เขียนฐานข้อมูล"""
from collections import defaultdict

from .db import get_db_connection
from .space_profile import SpaceProfileError


def summarize_spaces(rows):
    unique = {}
    for row in rows:
        key = str(row.get('SubArea_id') or '').strip()
        if not key or key in unique:
            raise SpaceProfileError('พบรหัสพื้นที่ว่างหรือซ้ำ ไม่สามารถสรุปยอดพื้นที่ได้')
        unique[key] = row
    counts = {'total': len(unique), 'occupied': 0, 'vacant': 0, 'other': 0}
    for row in unique.values():
        status = str(row.get('Status_Area') or '').strip()
        key = {'เช่าอยู่': 'occupied', 'ว่าง': 'vacant'}.get(status, 'other')
        counts[key] += 1
    counts['rate'] = round(counts['occupied'] * 100 / counts['total'], 2) if counts['total'] else None
    return counts


def grouped_spaces(rows, fields, names=None):
    groups = defaultdict(list)
    for row in rows:
        key = tuple(str(row.get(field) or '').strip() for field in fields)
        groups[key].append(row)
    result = []
    for key, members in groups.items():
        label = (names or {}).get(key) or ' / '.join(value or 'ไม่ระบุ' for value in key)
        result.append({'label': label, **summarize_spaces(members)})
    return sorted(result, key=lambda item: item['label'])


def dashboard_reference_data(year):
    conn = get_db_connection()
    try:
        conn.timeout = 30
        cursor = conn.cursor()
        cursor.execute('SELECT Location_id, Location_name FROM dbo.Contract_location_ms')
        locations = {(str(key).strip(),): str(name or key).strip() for key, name in cursor.fetchall()}
        cursor.execute('SELECT Location_id, Area_id, Area_name FROM dbo.Contract_location_area_ms')
        areas = {(str(location).strip(), str(area).strip()): str(name or area).strip()
                 for location, area, name in cursor.fetchall()}
        cursor.execute("""SELECT s.Snapshot_date, s.SubArea_id, s.Status_Area
            FROM dbo.Contract_Location_Snapshot s
            JOIN dbo.Contract_Location_Period p ON p.Period_date = s.Snapshot_date
            WHERE p.Period_status = 'CLOSED' AND s.Snapshot_date >= ? AND s.Snapshot_date < ?""",
            f'{year}-01-01', f'{year + 1}-01-01')
        months = defaultdict(list)
        for day, subarea, status in cursor.fetchall():
            months[day.month].append({'SubArea_id': subarea, 'Status_Area': status})
        return locations, areas, months
    finally:
        conn.close()
