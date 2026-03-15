from .models import Category , Budget , Transaction , User , Profile
from datetime import datetime

from django import forms
from django.contrib.auth.forms import PasswordChangeForm

# ไม่ได้ใช้
# class AdminUserForm(forms.ModelForm):
#     class Meta:
#         model = User
#         fields = ['username', 'email', 'is_active', 'is_staff', 'is_superuser']

# ยังใช้
class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField(label='อีเมล', widget=forms.TextInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(label='ชื่อจริง', required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(label='นามสกุล', required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email'] 
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ถ้ามี instance (คือ User ที่ล็อกอินอยู่) และเขามาจาก Google
        if self.instance.pk and self.instance.profile.is_google_login:
            self.fields['email'].disabled = True # ล็อคไม่ให้แก้
            self.fields['email'].help_text = "ล็อกอินผ่าน Google ไม่สามารถเปลี่ยนอีเมลได้"

# ยังใช้
class ProfileImageForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['profile_picture','avatar_color'] # ✅ แก้เป็น profile_picture
        labels = {'profile_picture': 'รูปโปรไฟล์',
                'avatar_color': 'สีของ Avatar'}
        widgets = {
            'profile_picture': forms.FileInput(attrs={'class': 'form-control'}),
            'avatar_color': forms.HiddenInput()
        }

# class ProfileForm(forms.ModelForm):
#     class Meta:
#         model = Profile
#         fields = ['profile_picture', 'password', 'info' ]
#         widgets = {
#             'profile_picture': forms.FileInput(),
#             'displayname' : forms.TextInput(attrs={'placeholder': 'Add display name'}),
#             'info' : forms.Textarea(attrs={'rows':3, 'placeholder': 'Add information'})
#         }

# ยังใช้
class SmartInputForm(forms.Form):
    raw_data = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': '(หากไม่พิมวันที่จะเป็นวันที่บันทึก) เช่น \n-50 ข้าวเช้า\n-20 ค่ารถ\n15000 เงินเดือน'
        }),
        label=''
    )

# ยังใช้
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

# import ใช้
class UploadFileForm(forms.Form):
    file = forms.FileField(
        label='เลือกไฟล์ Excel หรือ CSV',
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
    

# ใช้
class CategoryForm(forms.ModelForm):
    class Meta:
        print("Initializing CategoryForm Meta")
        model = Category
        fields = ['name', 'type','icon','color']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ชื่อหมวดหมู่'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ไอคอน'}),
            'color': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'สี (เช่น #FF0000)'}),
        }
        labels = {
            'name': 'ชื่อหมวดหมู่',
            'type': 'ประเภท',
            'icon': 'ไอคอน',
            'color': 'สี'
        }

# ใช้
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


