from django import forms


class ExcelUploadForm(forms.Form):
    excel_file = forms.FileField(label='ไฟล์ Excel (.xlsx)')

    def clean_excel_file(self):
        f = self.cleaned_data['excel_file']
        if not f.name.lower().endswith(('.xlsx', '.xls')):
            raise forms.ValidationError('รองรับเฉพาะไฟล์ .xlsx หรือ .xls เท่านั้น')
        return f
