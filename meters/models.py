"""
โมเดลเหล่านี้เป็นแค่ตัว "แมป" ไปยังตารางที่มีอยู่แล้วจริงในฐานข้อมูล SWU_contract
managed = False ทุกตัว -> Django จะไม่พยายามสร้าง/แก้ไข/ลบตารางเหล่านี้ให้เด็ดขาด
(การสร้าง/แก้ไขตารางทำผ่านไฟล์ .sql ที่ DBA รันเองเท่านั้น)

หมายเหตุ: Contract_location_subarea_ms มี Primary Key เป็น composite
(Location_id, Area_id, SubArea_id) ซึ่ง Django ORM ไม่รองรับ composite PK ตรงๆ
จึงไม่สร้างโมเดลสำหรับตารางนี้ - ใช้ raw SQL ใน services.py แทน
"""
from django.db import models


class ContractStatusMs(models.Model):
    status_contract_id = models.CharField(db_column='Status_contract_id', max_length=2, primary_key=True)
    status_contract_desc = models.CharField(db_column='Status_contract_Desc', max_length=100)

    class Meta:
        managed = False
        db_table = 'Contract_status_ms'

    def __str__(self):
        return f'{self.status_contract_id} - {self.status_contract_desc}'


class ContractHrdTr(models.Model):
    contract_id = models.IntegerField(db_column='Contract_id', primary_key=True)
    contract_code = models.CharField(db_column='Contract_code', max_length=50)
    contract_year = models.CharField(db_column='Contract_year', max_length=10, null=True)
    status_contract_id = models.CharField(db_column='Status_contract_id', max_length=2, null=True)

    class Meta:
        managed = False
        db_table = 'Contract_hrd_tr'

    def __str__(self):
        return self.contract_code


class ContractMeterMs(models.Model):
    """ทะเบียนมิเตอร์ (master) - สร้างโดย Contract_Meter_Setup.sql"""
    meter_id = models.AutoField(db_column='Meter_id', primary_key=True)
    location_id = models.CharField(db_column='Location_id', max_length=10)
    area_id = models.CharField(db_column='Area_id', max_length=10)
    subarea_id = models.CharField(db_column='SubArea_id', max_length=10)
    meter_type_cd = models.SmallIntegerField(db_column='Meter_type_cd')  # 8=ไฟฟ้า, 9=น้ำ
    meter_seq = models.IntegerField(db_column='Meter_seq')
    meter_no = models.CharField(db_column='Meter_no', max_length=50, null=True)
    meter_no_status = models.CharField(db_column='Meter_no_status', max_length=20)
    phase_type = models.CharField(db_column='Phase_type', max_length=10, null=True)
    use_or_not = models.BooleanField(db_column='UseOrNot', default=True)

    class Meta:
        managed = False
        db_table = 'Contract_meter_ms'

    @property
    def meter_type_label(self):
        return 'น้ำ' if self.meter_type_cd == 9 else 'ไฟฟ้า'

    def __str__(self):
        return f'{self.meter_type_label} #{self.meter_id} ({self.meter_no or "ไม่มีเลข"})'


class ContractMeterTr(models.Model):
    """การผูกมิเตอร์เข้ากับสัญญา - สร้างโดย Contract_Meter_Setup.sql"""
    contract_meter_seq = models.AutoField(db_column='Contract_meter_seq', primary_key=True)
    contract_id = models.IntegerField(db_column='Contract_id')
    location_id = models.CharField(db_column='Location_id', max_length=10)
    area_id = models.CharField(db_column='Area_id', max_length=10)
    subarea_id = models.CharField(db_column='SubArea_id', max_length=10)
    meter_id = models.IntegerField(db_column='Meter_id')
    use_or_not = models.BooleanField(db_column='UseOrNot', default=True)

    class Meta:
        managed = False
        db_table = 'Contract_meter_tr'
