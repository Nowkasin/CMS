"""
ตัวช่วยกลางที่หลาย view ใช้ร่วมกัน (วันที่ไทย/พ.ศ. และการแปลงค่าจากฟอร์ม)

เดิมฟังก์ชันพวกนี้กระจายอยู่ใน view แต่ละไฟล์ แล้ว view อื่น import ฟังก์ชัน private
(_safe_int, _period_label ฯลฯ) ข้ามไฟล์กันเอง หรือเขียนซ้ำคนละแบบ -- ย้ายมาไว้ที่เดียว
ไม่มีการเข้าถึงฐานข้อมูลในไฟล์นี้
"""
import datetime

THAI_MONTHS = [
    'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
]


def current_year_be():
    return datetime.date.today().year + 543


def year_options():
    """ตัวเลือกปี พ.ศ. ใน dropdown รอบบิล: ปีก่อน / ปีนี้ / ปีหน้า"""
    year = current_year_be()
    return [year - 1, year, year + 1]


def safe_int(raw, field_label, errors, min_value=None, max_value=None):
    """
    แปลงค่าเป็น int อย่างปลอดภัย -- แปลงไม่ได้หรือนอกช่วงจะไม่ throw แต่เพิ่มข้อความลง
    errors แล้วคืน None ให้ผู้เรียกข้ามค่านั้นไป ค่าว่างคืน None โดยไม่ถือว่า error

    ต้องตรวจช่วงด้วย เพราะ "แปลงเป็น int ได้" ยังไม่พอ เช่นเดือน 99 จะไปชน CHECK
    constraint ของตารางเลขอ่านเป็น error ดิบจากฐานข้อมูล
    """
    if raw is None or raw == '':
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        errors.append(f"{field_label} ต้องเป็นตัวเลขเท่านั้น (พิมพ์มาว่า '{raw}')")
        return None

    if min_value is not None and value < min_value:
        errors.append(f"{field_label} ต้องไม่น้อยกว่า {min_value} (พิมพ์มาว่า '{raw}')")
        return None
    if max_value is not None and value > max_value:
        errors.append(f"{field_label} ต้องไม่เกิน {max_value} (พิมพ์มาว่า '{raw}')")
        return None
    return value


def parse_iso_date(text):
    """'YYYY-MM-DD' -> date หรือ None ถ้าว่าง/ไม่ใช่วันที่จริง (เช่น 2569-02-31)"""
    try:
        return datetime.datetime.strptime((text or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def thai_date(value):
    """วันที่ -> '1 มิถุนายน 2569' (พ.ศ.) ตรงกับ thaiDate() ใน termination_detail.js"""
    if not value:
        return None
    try:
        return f'{value.day} {THAI_MONTHS[value.month - 1]} {value.year + 543}'
    except (AttributeError, IndexError, TypeError):
        return None


def thai_datetime(value, seconds=False):
    """datetime -> '2 พฤศจิกายน 2569 14:35' (หรือ 14:35:05 เมื่อ seconds=True)"""
    if not value:
        return None
    try:
        time_fmt = '%H:%M:%S' if seconds else '%H:%M'
        return f'{value.day} {THAI_MONTHS[value.month - 1]} {value.year + 543} {value:{time_fmt}}'
    except (AttributeError, IndexError, TypeError, ValueError):
        return None


def period_label(period):
    """
    งวดรูปแบบ YYYYMM -> ข้อความไทย เช่น '202702' -> 'กุมภาพันธ์ 2570'

    ปีในงวด (Installment_period / Last_installment_period) เก็บเป็น ค.ศ. ตามตารางงวดเดิม
    ห้ามเปลี่ยนค่าที่เก็บ แต่ตอนแสดงต้องเป็น พ.ศ. ให้ตรงกับที่อื่นในระบบ
    คืน None ถ้าไม่ใช่ YYYYMM -> เทมเพลต fallback ไปโชว์ค่าดิบ
    """
    text = str(period or '').strip()
    if len(text) != 6 or not text.isdigit():
        return None
    year_ce, month = int(text[:4]), int(text[4:])
    if not 1 <= month <= 12:
        return None
    return f'{THAI_MONTHS[month - 1]} {year_ce + 543}'


_THAI_DIGITS = ['', 'หนึ่ง', 'สอง', 'สาม', 'สี่', 'ห้า', 'หก', 'เจ็ด', 'แปด', 'เก้า']
_THAI_PLACES = ['', 'สิบ', 'ร้อย', 'พัน', 'หมื่น', 'แสน']


def _thai_number_words(number, after_million=False):
    """จำนวนเต็มบวก -> คำอ่านไทย (ล้านซ้อนกันได้ เช่น 1,000,000,000,000 = หนึ่งล้านล้าน)
    after_million -- ส่วนท้ายหลังคำว่าล้าน: หลักหน่วย 1 อ่าน "เอ็ด" (หนึ่งล้านเอ็ด)"""
    if number == 0:
        return ''
    if number >= 1_000_000:
        millions, rest = divmod(number, 1_000_000)
        return _thai_number_words(millions) + 'ล้าน' + _thai_number_words(rest, after_million=True)
    digits = str(number)
    words = []
    length = len(digits)
    for index, char in enumerate(digits):
        digit = int(char)
        place = length - index - 1
        if digit == 0:
            continue
        if place == 1 and digit == 1:
            words.append('สิบ')
        elif place == 1 and digit == 2:
            words.append('ยี่สิบ')
        elif place == 0 and digit == 1 and (length > 1 or after_million):
            words.append('เอ็ด')
        else:
            words.append(_THAI_DIGITS[digit] + _THAI_PLACES[place])
    return ''.join(words)


def baht_text(amount):
    """
    จำนวนเงิน -> คำอ่านบาทไทย เช่น 36300 -> 'สามหมื่นหกพันสามร้อยบาทถ้วน'
    ปัดสตางค์ 2 ตำแหน่งแบบปัดครึ่งขึ้น ใช้ในบรรทัด "รวมเป็นจำนวนเงิน" ของใบแจ้งหนี้
    (ใบแจ้งหนี้ K2 ใช้ udf_Num2Thai ของฐานข้อมูลกับราคาสัญญา แต่ที่นี่อ่านจากยอดรวมจริงของใบ
    จึงถูกต้องแม้ใบเดียวมีหลายบรรทัด)
    """
    from decimal import ROUND_HALF_UP, Decimal

    value = Decimal(str(amount or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    negative = value < 0
    value = abs(value)
    baht = int(value)
    satang = int((value - baht) * 100)
    if baht == 0 and satang == 0:
        return 'ศูนย์บาทถ้วน'
    text = ''
    if baht:
        text += _thai_number_words(baht) + 'บาท'
    text += (_thai_number_words(satang) + 'สตางค์') if satang else 'ถ้วน'
    return ('ลบ' if negative else '') + text


def expired_ago_label(end_date, today=None):
    """
    หมดอายุมานานเท่าไหร่ -> '6 ปี 4 เดือน', '3 เดือน', 'เดือนนี้'
    คืน None ถ้ายังไม่หมดอายุหรือไม่มีวันที่ นับแบบเดือนปฏิทินให้ตรงกับวิธีคิดงวด
    """
    if not end_date:
        return None
    today = today or datetime.date.today()
    if end_date >= today:
        return None

    months = (today.year - end_date.year) * 12 + (today.month - end_date.month)
    if today.day < end_date.day:
        months -= 1
    if months <= 0:
        return 'เดือนนี้'

    years, rem = divmod(months, 12)
    parts = []
    if years:
        parts.append(f'{years} ปี')
    if rem:
        parts.append(f'{rem} เดือน')
    return ' '.join(parts)
