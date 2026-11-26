import zipfile

from django import forms
from django.conf import settings

# นามสกุลที่รับได้ -- ไม่รับ .xls เพราะ openpyxl อ่านรูปแบบ BIFF เก่าไม่ได้เลย
# (ยืนยันแล้ว: load_workbook ไฟล์ .xls จริงได้ BadZipFile: File is not a zip file)
# เดิมฟอร์มรับ .xls ผ่าน แล้วไปพังที่ openpyxl เป็นหน้า 500
ALLOWED_EXTENSIONS = ('.xlsx', '.xlsm')

# ไฟล์ .xlsx เป็น zip ที่ต้องมีไฟล์นี้อยู่ข้างใน -- ใช้ยืนยันว่าเป็น Excel จริง
# ไม่ใช่ไฟล์อื่นที่เปลี่ยนนามสกุลมา
XLSX_MARKER = 'xl/workbook.xml'


class ExcelUploadForm(forms.Form):
    excel_file = forms.FileField(label='ไฟล์ Excel (.xlsx)')

    def clean_excel_file(self):
        """
        ตรวจ 3 ชั้นก่อนปล่อยให้ openpyxl อ่าน -- เดิมตรวจแค่นามสกุล ทำให้ไฟล์ที่
        เปลี่ยนชื่อมาหรือไฟล์ใหญ่เกินไปหลุดผ่านฟอร์มแล้วไปพังเป็นหน้า 500

        1) นามสกุล -- ตัด .xls ออกเพราะ openpyxl อ่านไม่ได้
        2) ขนาด    -- FILE_UPLOAD_MAX_MEMORY_SIZE ของ Django เป็นแค่เกณฑ์ว่าจะเก็บใน RAM
                      หรือเขียนเป็นไฟล์ชั่วคราว ไม่ใช่ขีดจำกัด ไฟล์ 500 MB ก็ผ่าน
                      แล้ว openpyxl จะกินหน่วยความจำจนล้ม จึงต้องจำกัดเอง
        3) เนื้อไฟล์ -- เช็คว่าเป็น zip และมี xl/workbook.xml อยู่จริง
        """
        f = self.cleaned_data['excel_file']

        name = (f.name or '').lower()
        if not name.endswith(ALLOWED_EXTENSIONS):
            raise forms.ValidationError(
                'รองรับเฉพาะไฟล์ .xlsx หรือ .xlsm เท่านั้น '
                '(ไฟล์ .xls รูปแบบเก่าอ่านไม่ได้ กรุณาเปิดด้วย Excel แล้ว Save As เป็น .xlsx)'
            )

        max_size = getattr(settings, 'EXCEL_UPLOAD_MAX_SIZE', 10 * 1024 * 1024)
        if f.size > max_size:
            raise forms.ValidationError(
                f'ไฟล์ใหญ่เกินกำหนด -- รับได้ไม่เกิน {max_size / 1024 / 1024:.0f} MB '
                f'(ไฟล์นี้ {f.size / 1024 / 1024:.1f} MB)'
            )

        # อ่านเนื้อไฟล์เพื่อตรวจ แล้วต้องเลื่อน pointer กลับที่ 0 เสมอ
        # ไม่งั้น openpyxl จะอ่านต่อจากตำแหน่งที่ค้างไว้แล้วพัง
        try:
            is_zip = zipfile.is_zipfile(f)
            f.seek(0)
            if not is_zip:
                raise forms.ValidationError(
                    'ไฟล์นี้ไม่ใช่ไฟล์ Excel ที่อ่านได้ -- อาจเป็นไฟล์ชนิดอื่นที่เปลี่ยนนามสกุลมา '
                    'หรือไฟล์เสียหาย'
                )
            if XLSX_MARKER not in zipfile.ZipFile(f).namelist():
                raise forms.ValidationError(
                    'ไฟล์นี้เป็นไฟล์บีบอัดแต่ไม่ใช่ Excel -- กรุณาตรวจสอบว่าเลือกไฟล์ถูกต้อง'
                )
        except forms.ValidationError:
            raise
        except Exception:
            # zipfile อ่านไม่ผ่านด้วยเหตุอื่น (ไฟล์เสียกลางทาง) -- ไม่โชว์ error ดิบ
            raise forms.ValidationError('อ่านไฟล์ไม่สำเร็จ -- ไฟล์อาจเสียหาย กรุณาลองไฟล์อื่น')
        finally:
            f.seek(0)

        return f


class SpacePeriodForm(forms.Form):
    month = forms.IntegerField(min_value=1, max_value=12)
    year = forms.IntegerField(min_value=2443, max_value=2643)


class SpaceFilterForm(forms.Form):
    business = forms.ChoiceField(label='ประเภทธุรกิจ', required=False)
    location = forms.ChoiceField(label='สถานที่ตั้ง', required=False)
    area_status = forms.ChoiceField(label='สถานะพื้นที่ย่อย', required=False)

    def __init__(self, *args, options, **kwargs):
        super().__init__(*args, **kwargs)
        for name, choices in options.items():
            self.fields[name].choices = choices


class SpacePeriodActionForm(forms.Form):
    period = forms.DateField(input_formats=['%Y-%m-%d'])
    action = forms.ChoiceField(choices=[('close', 'ปิดรอบ'), ('reopen', 'เปิดรอบ')])
    reason = forms.CharField(max_length=500, required=False)

    def clean(self):
        values = super().clean()
        if values.get('action') == 'reopen' and not values.get('reason'):
            self.add_error('reason', 'กรุณาระบุเหตุผลเปิดรอบ')
        return values


class SpaceDetailsForm(forms.Form):
    floor = forms.CharField(label='ชั้น', max_length=10)
    products = forms.CharField(label='ขายอะไร', max_length=255)
    business_type = forms.CharField(label='ประเภทธุรกิจ', max_length=255)
    shop_name = forms.CharField(label='ชื่อร้านค้า', max_length=255)
    purpose = forms.CharField(label='วัตถุประสงค์', max_length=255)

    def as_details(self):
        return dict(zip(
            ('Floor_BI', 'Shop_Sell_BI', 'Business_Types_BI', 'Shop_name_BI', 'Objective_Desc_BI'),
            (self.cleaned_data[name] for name in ('floor', 'products', 'business_type', 'shop_name', 'purpose')),
        ))
