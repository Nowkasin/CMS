"""
Template filter ของ CMS -- ใช้: {% load cms_text %} แล้ว {{ value|highlight:search }}
"""
import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def highlight(value, term):
    """
    ไฮไลต์คำค้นในข้อความด้วย <mark> (ไม่สนตัวพิมพ์เล็ก/ใหญ่)
    escape ข้อความทั้งหมดก่อนเสมอ แล้วจึงครอบเฉพาะส่วนที่ตรง -- ข้อมูลจากฐานข้อมูลจึงฉีด HTML ไม่ได้
    คำค้นที่มี * หรือ ? (wildcard ของช่องค้นหา) ไม่ไฮไลต์ เพราะตรงกับข้อความแบบไม่ต่อเนื่อง
    """
    text = '' if value is None else str(value)
    term = (term or '').strip()
    if not term or not text or '*' in term or '?' in term:
        return escape(text)
    parts = re.split(f'({re.escape(term)})', text, flags=re.IGNORECASE)
    html = ''.join(
        f'<mark class="rounded bg-amber-100 px-0.5 text-inherit">{escape(part)}</mark>'
        if index % 2 else escape(part)
        for index, part in enumerate(parts)
    )
    return mark_safe(html)
