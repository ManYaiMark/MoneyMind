from django import forms
from .models import Category , Budget , Transaction
from datetime import datetime

class SmartInputForm(forms.Form):
    raw_data = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'เช่น\nข้าวเช้า 50\nค่ารถ 20\n100 ค่าหวย'
        }),
        label=''
    )

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['date', 'description', 'amount', 'category']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'date': 'วันที่',
            'description': 'รายการ',
            'amount': 'จำนวนเงิน (ติดลบ=รายจ่าย)',
            'category': 'หมวดหมู่'
        }

# import 
class UploadFileForm(forms.Form):
    file = forms.FileField(
        label='เลือกไฟล์ Excel หรือ CSV',
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
    

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ชื่อหมวดหมู่'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'name': 'ชื่อหมวดหมู่',
            'type': 'ประเภท'
        }

class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ['category', 'amount_limit']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'amount_limit': forms.NumberInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'category': 'เลือกหมวดหมู่',
            'amount_limit': 'งบประมาณสูงสุด'
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['category'].queryset = Category.objects.filter(type='EXPENSE')


