import re
import json 
from datetime import datetime, timedelta
import pandas as pd
import io
import os
import tempfile
import csv
import calendar
import requests


from django.shortcuts import render, redirect, get_object_or_404  
# from django.dispatch import receiver
from django.http import HttpResponse, JsonResponse

from django.contrib import messages 
from django.contrib.auth import update_session_auth_hash ,get_user_model ,login
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required,user_passes_test

from django.db.models.functions import TruncDay, ExtractWeekDay ,TruncMonth
from django.db.models import Sum , Q , Count ,Case , When , FloatField ,Exists, OuterRef

from django.core.files.storage import FileSystemStorage
from django.core.files.base import ContentFile
from django.core.paginator import Paginator

from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timedelta,date

from .models import Transaction, Category, Budget  , CategoryKeyword  , User  ,SocialAccount
from .forms import  SmartInputForm, CategoryForm, BudgetForm , UploadFileForm , TransactionForm  , UserUpdateForm , ProfileImageForm
from .utils import predict_category_fuzzy
from allauth.account.views import PasswordResetView

# from .services import ai_classifier

def is_admin(user):
    return user.is_superuser

User = get_user_model()

# def confirm_account_link(request):
#     email = request.session.get('pending_google_email')
#     uid = request.session.get('pending_google_uid')
#     provider = request.session.get('pending_google_provider')
#     picture_url = request.session.get('pending_google_picture')
    
#     if not email:
#         return redirect('account_login')

#     if request.method == 'POST':
#         user = User.objects.filter(email__iexact=email).first()
#         if user:
#             SocialLinkConfirmation.objects.get_or_create(user=user)
            
#             if uid and provider:
#                 SocialAccount.objects.get_or_create(
#                     user=user,
#                     provider=provider,
#                     uid=uid
#                 )
            
#             if picture_url and not user.profile.profile_picture:
#                 try:
#                     response = requests.get(picture_url)
#                     if response.status_code == 200:
#                         file_name = f"{user.username}_google.jpg"
#                         user.profile.profile_picture.save(file_name, ContentFile(response.content), save=True)
#                 except Exception:
#                     pass
            
#             request.session.pop('pending_google_email', None)
#             request.session.pop('pending_google_uid', None)
#             request.session.pop('pending_google_provider', None)
#             request.session.pop('pending_google_picture', None)
            
#             login(request, user, backend='django.contrib.auth.backends.ModelBackend')
#             return redirect('dashboard')

#     return render(request, 'account/confirm_account_link.html', {'email': email})

# @login_required
# def profile_edit_view(request):
#     form = ProfileForm(instance=request.user.profile)  
    
#     if request.method == 'POST':
#         form = ProfileForm(request.POST, request.FILES, instance=request.user.profile)
#         if form.is_valid():
#             form.save()
#             return redirect('profile')
        
#     if request.path == reverse('profile-onboarding'):
#         onboarding = True
#     else:
#         onboarding = False

#     return render(request, 'a_users/profile_edit.html', { 'form':form, 'onboarding':onboarding })

@login_required
def profile(request):
    user = request.user
    default_color = get_random_color(user.id)
    current_color = user.profile.avatar_color or default_color
    
    u_form = UserUpdateForm(instance=user)
    img_form = ProfileImageForm(instance=user.profile)
    pass_form = PasswordChangeForm(user)

    if request.method == 'POST':
        if 'btn_update_image' in request.POST:
            img_form = ProfileImageForm(request.POST, request.FILES, instance=user.profile)
            if img_form.is_valid():
                profile_obj = img_form.save(commit=False)
                new_color = request.POST.get('avatar_color')
                
                if new_color and not request.FILES.get('profile_picture'):
                    profile_obj.profile_picture = None
                    profile_obj.avatar_color = new_color
                
                profile_obj.save()
                messages.success(request, 'อัปเดตรูปโปรไฟล์สำเร็จ!')
                return redirect('profile')

        elif 'btn_update_info' in request.POST:
            u_form = UserUpdateForm(request.POST, instance=user)
            if u_form.is_valid():
                u_form.save()
                messages.success(request, 'อัปเดตข้อมูลส่วนตัวสำเร็จ!')
                return redirect('profile')

    context = {
        'u_form': u_form,
        'img_form': img_form,
        'pass_form': pass_form,
        'current_color': current_color
    }
    return render(request, 'account/profile.html', context)

@login_required
def change_password_modal(request):
    if request.method == "POST":
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password1') 
        confirm_password = request.POST.get('new_password2') 
        
        user = request.user
        
        if not user.check_password(old_password):
            
            return JsonResponse({'status': 'error', 'message': 'รหัสผ่านเดิมไม่ถูกต้อง'}, status=400)
            
        if new_password != confirm_password:
            
            return JsonResponse({'status': 'error', 'message': 'ยืนยันรหัสผ่านใหม่ไม่ตรงกัน'}, status=400)
        
        user.set_password(new_password)
        user.save()
        update_session_auth_hash(request, user)
        messages.success(request, 'เปลี่ยนรหัสผ่านเรียบร้อยแล้ว ')
        
        return JsonResponse({'status': 'success', 'message': 'เปลี่ยนรหัสผ่านเรียบร้อยแล้ว '})
        
    return JsonResponse({'status': 'error', 'message': 'คำขอไม่ถูกต้อง'}, status=400)

@login_required
def set_password_modal(request):
    if request.method == "POST":
        new_password = request.POST.get('new_password1') 
        confirm_password = request.POST.get('new_password2') 
        
        user = request.user
        
        if user.has_usable_password():
            # messages.error(request, 'บัญชีนี้มีรหัสผ่านอยู่แล้ว')
            return JsonResponse({'status': 'error', 'message': 'บัญชีนี้มีรหัสผ่านอยู่แล้ว'}, status=400)
            
        if new_password != confirm_password:
            # messages.error(request, 'ยืนยันรหัสผ่านไม่ตรงกัน')
            return JsonResponse({'status': 'error', 'message': 'ยืนยันรหัสผ่านไม่ตรงกัน'}, status=400)
            
        if len(new_password) < 8:
            # messages.error(request, 'รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร')
            return JsonResponse({'status': 'error', 'message': 'รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร'}, status=400)
        
        user.set_password(new_password)
        user.save()
        update_session_auth_hash(request, user)
        
        messages.success(request, 'ตั้งรหัสผ่านเรียบร้อยแล้ว')
        return JsonResponse({'status': 'success', 'message': 'ตั้งรหัสผ่านเรียบร้อยแล้ว'})
        
    return JsonResponse({'status': 'error', 'message': 'คำขอไม่ถูกต้อง'}, status=400)


def get_random_color(user_id):
    colors = ['bg-primary', 'bg-success', 'bg-danger', 'bg-dark', 'bg-secondary', 'bg-info']
    return colors[user_id % len(colors)]



@login_required
def delete_account(request):
    if request.method == 'POST':
        user = request.user
        user.delete()
        messages.success(request, 'บัญชีของคุณถูกลบเรียบร้อยแล้ว')
        return redirect('account_login') # หรือ redirect ไปหน้า home
    
    # ถ้าเข้ามาด้วยวิธีอื่นที่ไม่ใช่ POST ให้เด้งกลับไปหน้า profile
    return redirect('profile')


@user_passes_test(is_admin)
def keyword_manager(request):
    """
    หน้าจัดการหมวดหมู่ระบบ (Global Categories)
    พร้อมแสดงสถิติการใช้งานจริง (Real Data)
    """
    
    # 1. หาจำนวน Transaction ทั้งหมดในระบบก่อน (เพื่อเอามาคำนวณ % ความนิยม)
    total_system_txns = Transaction.objects.count()

    # 2. ดึงข้อมูล Categories + นับจำนวนการใช้งานจริง (txn_count)
    # .annotate(txn_count=Count('transaction')) คือคำสั่ง SQL: "SELECT count(*) FROM transaction WHERE cat_id = ..."
    categories = Category.objects.filter(is_global=True).annotate(
        txn_count=Count('transaction')
    ).prefetch_related('categorykeyword_set').order_by('type', 'name')

    # 3. เตรียมข้อมูลสำหรับ Template
    for cat in categories:
        # --- ส่วนจัดการ Keyword เดิม ---
        keywords = [k.word for k in cat.categorykeyword_set.all()]
        cat.keyword_list = keywords
        cat.keyword_list_str = ",".join(keywords)

        # --- ส่วนคำนวณ % ความนิยม (Real Data) ---
        if total_system_txns > 0:
            
            percent = (cat.txn_count / total_system_txns) * 100
            cat.usage_percent = round(percent, 1) # ทศนิยม 1 ตำแหน่ง
        else:
            cat.usage_percent = 0


    
    # 4. แยกกลุ่มรายรับ/รายจ่าย
    expense_cats = [c for c in categories if c.type == 'EXPENSE']
    income_cats = [c for c in categories if c.type == 'INCOME']
    
    # นับ Keyword รวม (เหมือนเดิม)
    total_keywords_count = CategoryKeyword.objects.filter(category__is_global=True).count()
    total_Transactions = Transaction.objects.count()

    context = {
        'categories': categories,
        'expense_cats': expense_cats,
        'income_cats': income_cats,
        'total_keywords_count': total_keywords_count,
        'total_system_txns': total_system_txns,
        'total_Transactions': total_Transactions
    }
    
    return render(request, 'admin/keyword_manager.html', context)

@user_passes_test(is_admin)
def add_keyword(request):
    if request.method == "POST":
        # รับค่าจาก Form ใน Modal
        cat_id = request.POST.get('cat_id') # ถ้ามีค่า = แก้ไข, ถ้าว่าง = สร้างใหม่
        name = request.POST.get('name').strip()
        cat_type = request.POST.get('type')
        keywords_str = request.POST.get('keywords_list', '') # รับค่าเป็น string ยาวๆ เช่น "7-11,Grab,MK"

        if not name:
            messages.error(request, "กรุณาระบุชื่อหมวดหมู่")
            return redirect('keyword_manager')

        try:
            # ---------------------------------------------------
            # Step 1: จัดการตัวหมวดหมู่ (Category)
            # ---------------------------------------------------
            if cat_id:
                # --- กรณีแก้ไข (Edit) ---
                category = get_object_or_404(Category, id=cat_id)
                category.name = name
                category.type = cat_type
                category.save()
                action_msg = "อัปเดต"
            else:
                # --- กรณีสร้างใหม่ (Create) ---
                # เช็คชื่อซ้ำก่อน
                if Category.objects.filter(name__iexact=name, is_global=True).exists():
                    messages.warning(request, f"หมวดหมู่ '{name}' มีอยู่ในระบบแล้ว")
                    return redirect('keyword_manager')
                
                category = Category.objects.create(
                    name=name,
                    type=cat_type,
                    is_global=True, # บังคับเป็น Global เพราะ Admin สร้าง
                    user=None
                )
                action_msg = "สร้าง"

            # ---------------------------------------------------
            # Step 2: จัดการ Keywords (Sync Logic)
            # ---------------------------------------------------
            # แปลง string จากหน้าเว็บให้เป็น list (ตัดช่องว่างทิ้ง)
            new_keywords_list = [k.strip() for k in keywords_str.split(',') if k.strip()]
            
            # ดึง Keywords เดิมที่มีอยู่ใน Database ของหมวดนี้
            current_keywords = list(CategoryKeyword.objects.filter(category=category).values_list('word', flat=True))

            # หาความแตกต่าง (Set Operations)
            # 1. คำที่ต้องเพิ่ม (มีใน list ใหม่ แต่ไม่มีใน DB)
            to_add = set(new_keywords_list) - set(current_keywords)
            # 2. คำที่ต้องลบ (มีใน DB แต่ไม่มีใน list ใหม่ แปลว่าแอดมินลบออก)
            to_remove = set(current_keywords) - set(new_keywords_list)

            # ดำเนินการเพิ่ม
            if to_add:
                CategoryKeyword.objects.bulk_create([
                    CategoryKeyword(word=word, category=category) for word in to_add
                ])

            # ดำเนินการลบ
            if to_remove:
                CategoryKeyword.objects.filter(category=category, word__in=to_remove).delete()

            messages.success(request, f"{action_msg}หมวดหมู่ '{name}' และบันทึกคำศัพท์เรียบร้อยแล้ว")

        except Exception as e:
            messages.error(request, f"เกิดข้อผิดพลาด: {e}")
        
        return redirect('keyword_manager')

    # ถ้าไม่ใช่ POST ให้กลับหน้าหลัก
    return redirect('keyword_manager')

@user_passes_test(is_admin)
def admin_user_list(request):
    """ แสดงรายชื่อ และจัดการ CRUD เบื้องต้น """
    # ➕ ส่วนการ "เพิ่ม" ผู้ใช้ใหม่ (Create)
    if request.method == 'POST' and 'create_user' in request.POST:
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            if User.objects.filter(username=username).exists():
                messages.error(request, "ชื่อผู้ใช้นี้มีอยู่ในระบบแล้ว")
            else:
                user = User.objects.create_user(username=username, email=email, password=password)
                messages.success(request, f"สร้างผู้ใช้ {username} สำเร็จ")
        except Exception as e:
            messages.error(request, f"เกิดข้อผิดพลาด: {e}")
        return redirect('admin_user_list')
    
    google_account_exists = SocialAccount.objects.filter(
            user=OuterRef('pk'), 
            provider='google'
        )

    # 🔍 ระบบดึงข้อมูลเดิม
    users = User.objects.all().select_related('profile').annotate(
        has_google=Exists(google_account_exists)
    ).order_by('-date_joined')

    search_query = request.GET.get('q', '')
    if search_query:
        users = users.filter(Q(username__icontains=search_query) | Q(email__icontains=search_query))

    

    paginator = Paginator(users, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'admin/user_list.html', {
        'page_obj': page_obj, 
        'search_query': search_query
    })

@user_passes_test(is_admin)
def admin_user_edit(request, user_id):
    """ แก้ไขข้อมูลผู้ใช้ (Update) """
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        # 1. เช็กว่าคนนี้ผูก Google ไว้ไหม?
        has_google = SocialAccount.objects.filter(user=user, provider='google').exists()
        
        # 2. ถ้าไม่ได้ผูก Google ถึงจะอนุญาตให้แก้ชื่อและอีเมลได้
        if not has_google:
            user.username = request.POST.get('username')
            user.email = request.POST.get('email')
            
        # 3. เซฟสถานะ Active / Staff (แก้ได้ทุกคน)
        user.is_active = 'is_active' in request.POST
        user.is_staff = 'is_staff' in request.POST

        # 4. ส่วนเปลี่ยนรหัสผ่าน (ของคุณทำไว้ดีแล้ว)
        if request.POST.get('toggle_password') == 'on':
            new_password = request.POST.get('new_password', '').strip()
            
            if not user.has_usable_password():
                messages.error(request, "ไม่สามารถเปลี่ยนรหัสผ่านของบัญชี Google ได้")
                return redirect('admin_user_list')
                
            if len(new_password) < 8:
                messages.error(request, "รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร")
                return redirect('admin_user_list')
                
            user.set_password(new_password)
            messages.success(request, f"รีเซ็ตรหัสผ่านให้ {user.username} สำเร็จ")

        user.save()
        messages.success(request, f"อัปเดตข้อมูลของ {user.username} แล้ว")
        
    return redirect('admin_user_list')

@user_passes_test(is_admin)
def admin_user_delete(request, user_id):
    """ ลบผู้ใช้ออกจากระบบ (Delete) """
    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        messages.error(request, "คุณไม่สามารถลบตัวเองได้")
    else:
        username = user.username
        user.delete()
        messages.success(request, f"ลบผู้ใช้ {username} เรียบร้อยแล้ว")
    return redirect('admin_user_list')

@user_passes_test(is_admin)
def toggle_user_status(request, user_id):
    """ สลับสถานะผู้ใช้ (ระงับสิทธิ์ / เปิดใช้งาน) """
    target_user = get_object_or_404(User, id=user_id)
    
    # กันเหนียว: ห้าม Admin ระงับสิทธิ์ตัวเอง
    if target_user == request.user:
        messages.error(request, "คุณไม่สามารถระงับสิทธิ์ตัวเองได้!")
        return redirect('admin_user_list')
    
    target_user.is_active = not target_user.is_active
    target_user.save()
    
    status = "เปิดใช้งาน" if target_user.is_active else "ระงับสิทธิ์"
    messages.success(request, f"เปลี่ยนสถานะผู้ใช้ {target_user.username} เป็น {status} เรียบร้อย")
    return redirect('admin_user_list')

@user_passes_test(is_admin)
def delete_user_permanent(request, user_id):
    u = get_object_or_404(User, id=user_id)
    if u != request.user: # กัน Admin ลบตัวเอง
        u.delete()
        messages.success(request, f"ลบผู้ใช้ {u.username} ออกจากระบบถาวรแล้ว")
    return redirect('admin_user_list')


# ไม่ได้ใช้แล้ว เพราะย้ายไปใช้ fuzzy logic แทน
# @user_passes_test(is_admin)
# def ai_manager(request):
#     # 1. จัดการ Re-train
#     if request.method == 'POST' and 'retrain' in request.POST:
#         ai_classifier.train_model()
#         messages.success(request, "Re-train Model เรียบร้อยแล้ว!")
#         return redirect('ai_manager')

#     # 2. จัดการ Import CSV Training Data
#     if request.method == 'POST' and 'import_csv' in request.POST and request.FILES['csv_file']:
#         try:
#             csv_file = request.FILES['csv_file']
            
#             # ใช้ utf-8-sig เพื่อรองรับไฟล์จาก Excel/Notepad ที่มี BOM
#             decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
#             reader = csv.reader(decoded_file)
            
#             count = 0
#             created_cats = 0
            
#             for row in reader:
#                 # ข้ามบรรทัดหัวตาราง (ถ้าบรรทัดแรกคือคำว่า "คำศัพท์")
#                 if len(row) >= 1 and "คำศัพท์" in row[0]:
#                     continue

#                 if len(row) >= 2:
#                     text = row[0].strip()
#                     cat_name = row[1].strip()
                    
#                     if not text or not cat_name: continue

#                     # 1. หาหมวดหมู่ (ถ้าไม่มี ให้สร้างใหม่เลย!)
#                     cat = Category.objects.filter(name__iexact=cat_name).first()
#                     if not cat:
#                         # สร้างหมวดหมู่ใหม่ (Default ให้เป็นรายจ่ายไว้ก่อน)
#                         cat = Category.objects.create(
#                             name=cat_name, 
#                             type='EXPENSE', 
#                             is_global=True # ให้เป็น Global ไปเลยเพราะ Admin นำเข้า
#                         )
#                         created_cats += 1

#                     # 2. บันทึกลง Training Data (ถ้ายังไม่มีคำนี้)
#                     obj, created = TrainingData.objects.get_or_create(
#                         text=text,
#                         category=cat,
#                         defaults={'is_verified': True}
#                     )
#                     if created:
#                         count += 1
            
#             # Import เสร็จแล้ว Re-train ทันที
#             ai_classifier.train_model()
            
#             msg = f"นำเข้าศัพท์ใหม่ {count} คำ"
#             if created_cats > 0:
#                 msg += f" และสร้างหมวดหมู่ใหม่ {created_cats} หมวด"
            
#             messages.success(request, msg + " เรียบร้อย!")
            
#         except Exception as e:
#             messages.error(request, f"เกิดข้อผิดพลาด: {e}")
            
#         return redirect('ai_manager')

#     # แสดงข้อมูล Training Data ล่าสุด 20 รายการ
#     training_data = TrainingData.objects.all().order_by('-created_at')[:20]
    
#     return render(request, 'expenses/ai_manager.html', {'training_data': training_data})

# ไม่ได้ใช้แล้ว
@user_passes_test(is_admin)
def download_ai_template(request):
    # สร้าง response เป็นไฟล์ CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="ai_training_template.csv"'
    
    # เขียน BOM (Byte Order Mark) เพื่อให้ Excel เปิดภาษาไทยอ่านรู้เรื่อง
    response.write(u'\ufeff'.encode('utf8'))
    
    writer = csv.writer(response)
    
    # 1. เขียนหัวตาราง
    writer.writerow(['คำศัพท์', 'หมวดหมู่'])
    
    # 2. เขียนข้อมูลตัวอย่าง
    data = [
        ['7-Eleven', 'อาหาร'],
        ['ค่าวิน', 'เดินทาง'],
        ['Netflix', 'บันเทิง'],
        ['เงินเดือน', 'เงินเดือน'],
        ['ค่าหอ', 'ที่อยู่อาศัย'],
    ]
    
    writer.writerows(data)
    
    return response
   


@login_required
def add_smart_transaction(request):
    preview_data = None
    form = SmartInputForm()
    
    # ดึงหมวดหมู่สำหรับ Dropdown (ใช้ตอนแก้ไข)
    income_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='INCOME').order_by('name')
    expense_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='EXPENSE').order_by('name')

    if request.method == 'POST':
        # ---------------------------------------------------------
        # CASE A: ยืนยันการบันทึก (Confirm Save)
        # ---------------------------------------------------------
        if 'confirm_save' in request.POST:
            try:
                json_data = request.POST.get('final_data')
                try:
                    data_list = json.loads(json_data)
                    # บางที json.loads อาจจะได้ string ซ้อนอีกที ให้แกะอีกรอบ
                    if isinstance(data_list, str): 
                        data_list = json.loads(data_list)
                except (ValueError, TypeError): 
                    data_list = []

                txns = []
                for item in data_list:
                    # ป้องกันข้อมูลเพี้ยน
                    if isinstance(item, str):
                        try: item = json.loads(item)
                        except: continue
                    
                    # แปลงวันที่
                    try: 
                        date_obj = datetime.strptime(item.get('date', ''), '%Y-%m-%d').date()
                    except: 
                        date_obj = datetime.now().date()
                    
                    # หา Category Object
                    cat_obj = None
                    if item.get('cat_id'):
                        cat_obj = Category.objects.filter(id=item['cat_id']).first()
                    
                    # สร้าง Transaction Object เตรียมไว้
                    txns.append(Transaction(
                        user=request.user,
                        description=item.get('description', ''),
                        amount=float(item.get('amount', 0)),
                        date=date_obj,
                        category=cat_obj
                    ))
                
                # บันทึกทีเดียว (Bulk Create)
                if txns:
                    Transaction.objects.bulk_create(txns)
                    messages.success(request, f"✅ บันทึกสำเร็จ {len(txns)} รายการ!")
                    return redirect('dashboard') # หรือหน้า Transaction List
                else:
                    messages.warning(request, "ไม่มีข้อมูลให้บันทึก")

            except Exception as e:
                messages.error(request, f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}")

        # ---------------------------------------------------------
        # CASE B: ประมวลผลข้อความ (Process Smart Input)
        # ---------------------------------------------------------
        else:
            form = SmartInputForm(request.POST)
            if form.is_valid():
                raw_data = form.cleaned_data['raw_data']
                lines = raw_data.strip().split('\n')
                preview_list = []
                current_date = datetime.now().date()
                
                # เตรียมหมวด "อื่นๆ" ไว้เป็น Fallback
                fallback_cat = Category.objects.filter(name="อื่นๆ", is_global=True).first()

                for line in lines:
                    line = line.strip()
                    if not line: continue

                    # 1. แกะวันที่ (Regex)
                    date_obj = current_date
                    # Pattern: 12-12, 12/12/2566
                    date_match = re.search(r'\b(\d{1,2})[-/](\d{1,2})(?:[-/](\d{2,4}))?\b', line)
                    
                    if date_match:
                        d, m, y_str = date_match.groups()
                        try:
                            year = int(y_str) if y_str else current_date.year
                            if year < 100: year += 2000 
                            if year > 2400: year -= 543 # แก้ พ.ศ.
                            date_obj = datetime(year, int(m), int(d)).date()
                            line = line.replace(date_match.group(0), '').strip() # ลบวันที่ออกจากข้อความ
                        except ValueError:
                            pass

                    # 2. แกะจำนวนเงิน และ ชื่อรายการ
                    description = "รายการทั่วไป"
                    final_amount = 0.0
                    num_re = r'([+-]?[0-9,]+(?:\.\d+)?)' # Regex จับตัวเลข

                    match_front = re.match(r'^' + num_re + r'\s+(.*)$', line) # "100 ค่าข้าว"
                    match_back = re.match(r'^(.*)\s+' + num_re + r'$', line)  # "ค่าข้าว 100"

                    amount_str = "0"
                    
                    if match_front:
                        amount_str = match_front.group(1)
                        description = match_front.group(2).strip()
                    elif match_back:
                        description = match_back.group(1).strip()
                        amount_str = match_back.group(2)
                    else:
                        # กรณีพิมพ์มาแต่ตัวเลข
                        try:
                            test_amt = float(line.replace(',', ''))
                            amount_str = line
                            description = "รายการทั่วไป"
                        except ValueError:
                            continue # ข้ามบรรทัดที่อ่านไม่ออก

                    # แปลงเงินเป็น float
                    try:
                        amount_val = float(amount_str.replace(',', ''))
                        if '-' in amount_str:
                            final_amount = -abs(amount_val)
                        else:
                            final_amount = abs(amount_val)
                    except ValueError:
                        continue

                    # 3. 🤖 ทำนายหมวดหมู่ (Prediction Logic)
                    cat_id = ""
                    category_name = "-"
                    cat_icon = "bi-question-circle" # Default Icon
                    cat_color = "secondary"         # Default Color
                    is_uncertain = False            # Flag ความไม่มั่นใจ

                    # 3.1 เช็คประวัติเป๊ะๆ (History Exact Match)
                    prev = Transaction.objects.filter(user=request.user, description__iexact=description).order_by('-created_at').first()
                    
                    if prev and prev.category:
                        # ถ้าเจอในประวัติ -> มั่นใจ 100%
                        cat_id = prev.category.id
                        category_name = prev.category.name
                        cat_icon = prev.category.icon
                        cat_color = prev.category.color
                    
                    else:
                        # 3.2 ใช้ Fuzzy Logic (AI)
                        # *ต้องแน่ใจว่า import ฟังก์ชัน predict_category_fuzzy มาแล้ว*
                        predicted_cat, matched_word, score = predict_category_fuzzy(description)
                        
                        if predicted_cat:
                            cat_id = predicted_cat.id
                            category_name = predicted_cat.name
                            cat_icon = predicted_cat.icon
                            cat_color = predicted_cat.color
                            
                            # ถ้าคะแนนต่ำกว่า 70 -> ไม่มั่นใจ
                            if score < 70:
                                is_uncertain = True
                        else:
                            # 3.3 หาไม่เจอเลย -> ลงหมวด "อื่นๆ" (ไม่มั่นใจ)
                            if fallback_cat:
                                cat_id = fallback_cat.id
                                category_name = fallback_cat.name
                                cat_icon = fallback_cat.icon
                                cat_color = fallback_cat.color
                                is_uncertain = True # เตือน User หน่อยว่าระบบเลือกให้อัตโนมัติ
                            else:
                                category_name = "-"
                                is_uncertain = True

                    # 4. เพิ่มลง List เตรียมแสดงผล
                    preview_list.append({
                        'date': date_obj.strftime('%Y-%m-%d'),
                        'description': description,
                        'amount': final_amount,
                        'cat_id': cat_id,
                        'category_name': category_name,
                        'icon': cat_icon,       # ส่ง Icon ไป
                        'color': cat_color,     # ส่ง Color ไป
                        'is_uncertain': is_uncertain # ส่งสถานะความมั่นใจไป
                    })
                    
                preview_data = preview_list 

    return render(request, 'expenses/add_smart.html', {
        'form': form, 
        'preview_data': preview_data,
        'income_cats': income_cats,
        'expense_cats': expense_cats
    })


@login_required
def import_data(request):
    preview_data = None
    form = UploadFileForm()

    fallback_cat = Category.objects.filter(name="อื่นๆ", is_global=True).first()

    if request.method == 'POST':
        if 'confirm_save' in request.POST:
            try:
                json_data = request.POST.get('final_data')
                try:
                    data_list = json.loads(json_data)
                    if isinstance(data_list, str): data_list = json.loads(data_list)
                except ValueError: data_list = []
                
                txns = []
                for item in data_list:
                    if isinstance(item, str):
                        try: item = json.loads(item)
                        except: continue

                    try: date_obj = datetime.strptime(item.get('date', ''), '%Y-%m-%d').date()
                    except: date_obj = datetime.now().date()

                    cat_obj = None
                    if item.get('cat_id'):
                        cat_obj = Category.objects.filter(id=item['cat_id']).first()
                    
                    txns.append(Transaction(
                        user=request.user,
                        description=item.get('description', ''),
                        amount=float(item.get('amount', 0)),
                        date=date_obj,
                        category=cat_obj
                    ))
                
                if txns:
                    Transaction.objects.bulk_create(txns)
                    messages.success(request, f"นำเข้าสำเร็จ {len(txns)} รายการ!")
                    return redirect('dashboard')
                else:
                    messages.warning(request, "ไม่มีข้อมูลให้บันทึก")

            except Exception as e:
                messages.error(request, f"เกิดข้อผิดพลาด: {e}")

        else:
            form = UploadFileForm(request.POST, request.FILES)
            if form.is_valid():
                file = request.FILES['file']
                tmp_file_path = None
                
                try:
                    suffix = '.xlsx'
                    if file.name.endswith('.csv'): suffix = '.csv'
                    elif file.name.endswith('.xls'): suffix = '.xls'
                    elif file.name.endswith('.txt'): suffix = '.txt'
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        for chunk in file.chunks():
                            tmp.write(chunk)
                        tmp_file_path = tmp.name

                    df = pd.DataFrame()
                    data_list = []

                    if file.name.endswith('.txt'):
                        current_date = datetime.now().date()
                        with open(tmp_file_path, 'r', encoding='utf-8') as f:
                            for line in f:
                                line = line.strip()
                                if not line: continue
                                
                                date_obj = current_date # ตั้งต้นเป็นวันนี้
                    
                                # Pattern วันที่: จับกลุ่ม (วัน)/(เดือน)/(ปี หรือไม่มีก็ได้)
                                date_match = re.search(r'\b(\d{1,2})[-/](\d{1,2})(?:[-/](\d{2,4}))?\b', line)
                                
                                if date_match:
                                    d, m, y_str = date_match.groups()
                                    try:
                                        year = int(y_str) if y_str else current_date.year
                                        # แปลงปี 2 หลัก (เช่น 66 -> 2566 -> 2023 หรือ 26 -> 2026)
                                        if year < 100: year += 2000 
                                        # ถ้าปีเป็น พ.ศ. (มากกว่า 2400) ให้ลบ 543
                                        if year > 2400: year -= 543
                                            
                                        date_obj = datetime(year, int(m), int(d)).date()
                                        
                                    except ValueError:
                                        pass # ถ้าวันที่พัง ใช้วันปัจจุบัน
                                
                                amount_match = re.search(r'([+-]?[0-9,]+(\.\d+)?)', line)
                                if amount_match:
                                    amt_str = amount_match.group(1)
                                    try:
                                        amount_val = float(amt_str.replace(',', ''))
                                    except ValueError: continue
                                    
                                    if '-' in amt_str: final_amount = -abs(amount_val)
                                    else: final_amount = abs(amount_val)

                                    description = line.replace(amt_str, '').strip() or "รายการทั่วไป"
                                    data_list.append({'date': current_date, 'amount': final_amount, 'description': description, 'category': None})
                        
                        df = pd.DataFrame(data_list)
                    
                    else:
                        if file.name.endswith('.csv'): df = pd.read_csv(tmp_file_path, encoding='utf-8-sig')
                        elif file.name.endswith('.xls'): df = pd.read_excel(tmp_file_path, engine='xlrd')
                        else: df = pd.read_excel(tmp_file_path, engine='openpyxl')
                        
                        df.columns = df.columns.str.strip()
                        column_mapping = {
                            'วันที่': 'date', 'Date': 'date', 'date': 'date',
                            'รายการ': 'description', 'Description': 'description', 'description': 'description',
                            'จำนวนเงิน': 'amount', 'Amount': 'amount', 'amount': 'amount', 'จำนวน': 'amount',
                            'หมวดหมู่': 'category', 'Category': 'category', 'category': 'category'
                        }
                        df.rename(columns=column_mapping, inplace=True)

                    preview_list = []
                    
                    if 'amount' in df.columns and 'description' in df.columns:
                        df.dropna(subset=['amount', 'description'], inplace=True)
                        
                        for _, row in df.iterrows():
                            try:
                                amt_raw = row['amount']
                                if isinstance(amt_raw, str):
                                    amt_raw = amt_raw.replace(',', '')
                                
                                amt = float(amt_raw)
                                if pd.isna(amt): continue

                                if 'date' in df.columns:
                                    raw_date = row['date']
                                    if isinstance(raw_date, str):
                                        txn_date = pd.to_datetime(raw_date, dayfirst=True).date()
                                    elif isinstance(raw_date, (datetime, pd.Timestamp)):
                                        txn_date = raw_date.date()
                                    else:
                                        txn_date = datetime.now().date()
                                else:
                                    txn_date = datetime.now().date()

                                description = str(row['description']).strip()

                                cat_id = ""
                                cat_name = "-"
                                cat_icon = "bi-question-circle" # ไอคอนมาตรฐาน
                                cat_color = "secondary"         # สีมาตรฐาน
                                is_uncertain = False            # ตัวแปรเช็คความมั่นใจ

                                # 1. เช็คว่าในไฟล์ระบุหมวดหมู่มาไหม (มั่นใจ 100%)
                                if 'category' in df.columns and pd.notna(row['category']):
                                    cat_name_str = str(row['category']).strip()
                                    c = Category.objects.filter(name__iexact=cat_name_str).first()
                                    if c: 
                                        cat_id, cat_name, cat_icon, cat_color = c.id, c.name, c.icon, c.color

                                # 2. ถ้าไม่มี ให้เช็คประวัติเก่า (มั่นใจ 100%)
                                if not cat_id:
                                    prev = Transaction.objects.filter(user=request.user, description__iexact=description).order_by('-created_at').first()
                                    if prev and prev.category:
                                        cat_id = prev.category.id
                                        cat_name = prev.category.name
                                        cat_icon = prev.category.icon
                                        cat_color = prev.category.color

                                # 3. ถ้าไม่มีประวัติ -> ใช้ Fuzzy Logic
                                if not cat_id:
                                    predicted_cat, matched_word, score = predict_category_fuzzy(description)
                                    if predicted_cat:
                                        cat_id = predicted_cat.id
                                        cat_name = predicted_cat.name
                                        cat_icon = predicted_cat.icon
                                        cat_color = predicted_cat.color
                                        # ถ้าคะแนนเดาน้อยกว่า 75 ให้ขึ้นเตือนว่าไม่มั่นใจ
                                        if score < 75:
                                            is_uncertain = True
                                    
                                    # 4. สุดท้ายถ้าหาไม่เจอจริงๆ ลง "อื่นๆ"
                                    elif fallback_cat:
                                        cat_id = fallback_cat.id
                                        cat_name = fallback_cat.name
                                        cat_icon = fallback_cat.icon
                                        cat_color = fallback_cat.color
                                        is_uncertain = True # ลงหมวดอื่นๆ อัตโนมัติควรให้ User ตรวจสอบ

                                # บันทึกลง Preview List พร้อมข้อมูลใหม่
                                preview_list.append({
                                    'date': txn_date.strftime('%Y-%m-%d'),
                                    'description': description,
                                    'amount': amt,
                                    'cat_id': cat_id,
                                    'category_name': cat_name,
                                    'icon': cat_icon,       # เพิ่มเข้าไป
                                    'color': cat_color,     # เพิ่มเข้าไป
                                    'is_uncertain': is_uncertain # เพิ่มเข้าไป
                                })
                            except: continue
                    else:
                        missing = []
                        if 'amount' not in df.columns: missing.append('จำนวนเงิน (Amount)')
                        if 'description' not in df.columns: missing.append('รายการ (Description)')
                        messages.error(request, f"ไฟล์ไม่ถูกต้อง ขาดคอลัมน์: {', '.join(missing)}")

                    if preview_list:
                        preview_data = preview_list
                    else:
                        if not messages.get_messages(request):
                            messages.warning(request, "ไม่พบข้อมูลรายการในไฟล์")

                except Exception as e:
                    messages.error(request, f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")
                finally:
                    if tmp_file_path and os.path.exists(tmp_file_path): os.remove(tmp_file_path)
            
            else:
                messages.error(request, f"ข้อมูลไฟล์ไม่ถูกต้อง: {form.errors}")

    income_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='INCOME').order_by('name')
    expense_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='EXPENSE').order_by('name')

    return render(request, 'expenses/import_data.html', {
        'form': form, 
        'preview_data': preview_data,
        'income_cats': income_cats,
        'expense_cats': expense_cats
    })


# ฟังก์ชัน download_template 
@login_required
def download_template(request):
    file_format = request.GET.get('format', 'xlsx')
    
    data = {
        'วันที่': ['25/12/2025', '26/12/2025'],
        'รายการ': ['เงินเดือน', 'ค่าอาหาร'],
        'จำนวนเงิน': [25000, -150],
        'หมวดหมู่': ['เงินเดือน', 'อาหาร']
    }
    
    if file_format == 'csv':
        df = pd.DataFrame(data)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="moneymind_template.csv"'
        df.to_csv(response, index=False, encoding='utf-8-sig')
        return response
    
    elif file_format == 'txt':
        content = """25/12/2025
25000 เงินเดือน
-150 ค่าอาหาร
26/12/2025
-150 ค่าอาหาร
27/12/2025
-500 ค่าหวย"""
        response = HttpResponse(content, content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename="moneymind_template.txt"'
        return response
        
    else: 
        df = pd.DataFrame(data)
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="moneymind_template.xlsx"'
        df.to_excel(response, index=False)
        return response
    


@login_required
def dashboard(request):
    if request.user.is_superuser:
        return redirect('admin_user_list')

    # --- 1. จัดการวันที่ (Reference Date) ---
    today = timezone.now().date()
    date_str = request.GET.get('date')
    try:
        ref_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else today
    except ValueError:
        ref_date = today

    curr_month, curr_year = ref_date.month, ref_date.year
    days_in_month = calendar.monthrange(curr_year, curr_month)[1]
    month_start = date(curr_year, curr_month, 1)
    month_end = date(curr_year, curr_month, days_in_month)

    # --- 2. ส่วนสรุปตัวเลขสำคัญ (Overview Cards) ---
    total_balance = float(Transaction.objects.filter(user=request.user).aggregate(
        balance=Sum('amount'))['balance'] or 0)

    monthly_stats = Transaction.objects.filter(
        user=request.user, 
        date__range=[month_start, month_end]
    ).aggregate(
        income=Sum(Case(When(amount__gt=0, then='amount'), output_field=FloatField())),
        expense=Sum(Case(When(amount__lt=0, then='amount'), output_field=FloatField()))
    )
    
    m_income = float(monthly_stats['income'] or 0)
    m_expense = float(abs(monthly_stats['expense'] or 0))
    
    budget_query = Budget.objects.filter(user=request.user, month=curr_month, year=curr_year)
    total_budget = float(budget_query.aggregate(Sum('amount_limit'))['amount_limit__sum'] or 0)
    remaining_budget = total_budget - m_expense

    # --- 3. ข้อมูลกราฟ (Visualizations) ---
    
    # 🎨 ระบบแมปสีจากชื่อคลาส Bootstrap เป็น Hex Code สำหรับ Chart.js
    COLOR_MAP = {
        'primary': '#0d6efd',
        'success': '#198754',
        'danger': '#dc3545',
        'warning': '#ffc107',
        'info': '#0dcaf0',
        'secondary': '#6c757d',
        'dark': '#212529',
        'light': '#f8f9fa',
    }

    # A. Pie Chart (สัดส่วนรายจ่าย)
    pie_data = Transaction.objects.filter(
        user=request.user, date__range=[month_start, month_end], amount__lt=0
    ).values('category__name', 'category__color').annotate(total=Sum('amount'))
    
    pie_labels = [item['category__name'] or "ไม่ระบุ" for item in pie_data]
    pie_values = [float(abs(item['total'])) for item in pie_data]
    
    # ✅ แก้ไขเรื่องสี: ตรวจสอบและแปลงเป็น Hex Code
    pie_colors = []
    for item in pie_data:
        color_name = item['category__color']
        # ถ้าชื่อสีอยู่ใน Map ให้ดึงรหัสมา ถ้าไม่อยู่ให้ใช้สีเทา
        hex_color = COLOR_MAP.get(color_name, '#858796') 
        pie_colors.append(hex_color)

    # B. Bar Chart (รายรับ vs รายจ่าย 6 เดือน)
    six_months_ago = month_start - timedelta(days=180)
    bar_data = Transaction.objects.filter(
        user=request.user, date__range=[six_months_ago, month_end]
    ).annotate(month_label=TruncMonth('date')).values('month_label').annotate(
        inc=Sum(Case(When(amount__gt=0, then='amount'), output_field=FloatField())),
        exp=Sum(Case(When(amount__lt=0, then='amount'), output_field=FloatField()))
    ).order_by('month_label')

    bar_labels = [item['month_label'].strftime('%b %Y') for item in bar_data]
    bar_income = [float(item['inc'] or 0) for item in bar_data]
    bar_expense = [float(abs(item['exp'] or 0)) for item in bar_data]


    # C. Line Chart (กระแสเงินสดสะสม)
    opening_balance = float(Transaction.objects.filter(
        user=request.user, 
        date__lt=month_start
    ).aggregate(Sum('amount'))['amount__sum'] or 0)

    daily_txns = Transaction.objects.filter(
        user=request.user, date__range=[month_start, month_end]
    ).annotate(day=TruncDay('date')).values('day').annotate(daily_sum=Sum('amount')).order_by('day')
    
    line_labels = [str(i) for i in range(1, days_in_month + 1)]
    line_values = []

    running_balance = total_balance - (m_income - m_expense) 
    daily_map = {item['day'].day: float(item['daily_sum'] or 0) for item in daily_txns}

    current_running_balance = opening_balance
    
    for d in range(1, days_in_month + 1):
        current_running_balance += daily_map.get(d, 0.0)
        
        if ref_date.year < today.year or (ref_date.year == today.year and ref_date.month < today.month):
            line_values.append(current_running_balance)
        elif d <= today.day:
            line_values.append(current_running_balance)

    # --- 4. ข้อมูลเชิงลึก & เป้าหมาย ---
    recent_transactions = Transaction.objects.filter(user=request.user,date__range=[month_start, month_end]).order_by('-date', '-created_at')[:5]
    top_cat = pie_data.order_by('total').first()
    top_spending_cat = top_cat['category__name'] if top_cat else "ไม่มีข้อมูล"
    
    # savings_amount = m_income - m_expense
    # savings_rate = round((savings_amount / m_income * 100), 1) if m_income > 0 else 0

    net_cash_flow = m_income - m_expense

    budget_query = Budget.objects.filter(user=request.user, month=curr_month, year=curr_year)
    budget_status_list = []

    for b in budget_query:
        # คำนวณยอดที่ใช้ไปในหมวดนี้
        spent = abs(float(Transaction.objects.filter(
            user=request.user, 
            category=b.category, 
            date__range=[month_start, month_end]
        ).aggregate(Sum('amount'))['amount__sum'] or 0))
        
        limit = float(b.amount_limit) #
        remaining = limit - spent
        percent = (spent / limit * 100) if limit > 0 else 0
        
        budget_status_list.append({
            'name': b.category.name,
            'remaining': remaining,
            'percent': round(percent, 1),
            'limit': limit
        })

    
    critical_budget = None
    if budget_status_list:
        critical_budget = sorted(budget_status_list, key=lambda x: x['remaining'])[0]

    budget_alerts = []
    for b in budget_query:
        spent = abs(float(Transaction.objects.filter(user=request.user, category=b.category, 
                    date__range=[month_start, month_end]).aggregate(Sum('amount'))['amount__sum'] or 0))
        limit = float(b.amount_limit)
        percent = (spent / limit) * 100 if limit > 0 else 0
        if percent >= 80:
            budget_alerts.append({'name': b.category.name, 'percent': round(percent, 1)})

    thai_months = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    
    context = {
        'total_balance': total_balance, 'm_income': m_income, 'm_expense': m_expense,
        'remaining_budget': remaining_budget, 'critical_budget': critical_budget,'net_cash_flow': net_cash_flow,
        # 'savings_rate': savings_rate, 'savings_amount': savings_amount,
        'pie_labels': json.dumps(pie_labels), 'pie_values': json.dumps(pie_values), 'pie_colors': json.dumps(pie_colors),
        'bar_labels': json.dumps(bar_labels), 'bar_income': json.dumps(bar_income), 'bar_expense': json.dumps(bar_expense),
        'line_labels': json.dumps(line_labels), 'line_values': json.dumps(line_values),
        'recent_transactions': recent_transactions, 'top_spending_cat': top_spending_cat,
        'budget_alerts': budget_alerts, 'current_month_name': thai_months[curr_month],
        'current_year': curr_year + 543, 'prev_month_url': f"?date={month_start - timedelta(days=1)}",
        'next_month_url': f"?date={month_end + timedelta(days=1)}",
    }
    return render(request, 'expenses/dashboard.html', context)


@login_required
def transaction_list(request):
    # 1. ดึงข้อมูลพื้นฐาน
    transactions = Transaction.objects.filter(user=request.user)
    total_count = transactions.count()

    # ✅ รายการวันที่ที่มีธุรกรรม (ส่งไปจางสีในปฏิทิน)
    active_dates = list(transactions.values_list('date', flat=True).distinct())
    active_dates_json = json.dumps([d.strftime('%Y-%m-%d') for d in active_dates])

    # 2. รับค่า Filter
    query = request.GET.get('q', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    category_id = request.GET.get('category', '')

    # 3. Filter Logic
    if query:
        transactions = transactions.filter(description__icontains=query)
    if start_date and end_date:
        transactions = transactions.filter(date__range=[start_date, end_date])
    if category_id:
        transactions = transactions.filter(category_id=category_id)

    # 4. จัดเรียงข้อมูล
    transactions = transactions.order_by('-date', '-created_at')
    
    # 5. เตรียมข้อมูล Dropdown และข้อมูลส่งกลับหน้าเว็บ
    income_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='INCOME').order_by('name')
    expense_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='EXPENSE').order_by('name')
    
    # หาชื่อหมวดหมู่ที่ถูกเลือกเพื่อไปแสดงที่ปุ่ม Dropdown
    selected_cat_name = "ทั้งหมด"
    if category_id:
        cat_obj = Category.objects.filter(id=category_id).first()
        if cat_obj:
            selected_cat_name = cat_obj.name

    context = {
        'transactions': transactions,
        'income_cats': income_cats,
        'expense_cats': expense_cats,
        'total_count': total_count,
        'filtered_count': transactions.count(),
        'search_query': query,
        'start_date': start_date,
        'end_date': end_date,
        'category_id': category_id,
        'category_name': selected_cat_name,
        'active_dates_json': active_dates_json,
    }
    return render(request, 'expenses/transaction_list.html', context)


@login_required
def edit_transaction(request, transaction_id):
    transaction = get_object_or_404(Transaction, id=transaction_id, user=request.user)
    
    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            # เก็บค่าก่อน save เพื่อดูว่ามีการเปลี่ยนหมวดหมู่ไหม
            old_category = transaction.category 
            updated_txn = form.save()
            
            # --- AI Learning Trigger 🧠 ---
            
            # if updated_txn.category != old_category:
            #     # สั่งให้ AI จำคำนี้คู่กับหมวดหมู่ใหม่ทันที!
            #     ai_classifier.learn(
            #         text=updated_txn.description,
            #         category_obj=updated_txn.category,
            #         user=request.user
            #     )
            

            new_category = updated_txn.category
            if old_category != new_category:
                messages.info(request, "คุณได้เปลี่ยนหมวดหมู่ของรายการนี้")
            messages.success(request, "แก้ไขรายการเรียบร้อย!")

            return redirect('transaction_list')
    else:
        form = TransactionForm(instance=transaction)
    
    return redirect('transaction_list')


@login_required
def delete_transaction(request, transaction_id):
    transaction = get_object_or_404(Transaction, id=transaction_id, user=request.user)
    transaction.delete()
    messages.success(request, "ลบรายการเรียบร้อย!")
    return redirect('transaction_list')

@login_required
def delete_multiple_transactions(request):
    if request.method == 'POST':
        transaction_ids = request.POST.getlist('transaction_ids')
        if transaction_ids:
            Transaction.objects.filter(id__in=transaction_ids, user=request.user).delete()
            messages.success(request, f"ลบข้อมูลที่เลือกเรียบร้อยแล้ว!")
        else:
            messages.warning(request, "ไม่ได้เลือกรายการใดๆ")
    return redirect('transaction_list')


@login_required
def manage_categories(request):
    categories = Category.objects.filter(
        Q(is_global=True) | Q(user=request.user)
    ).order_by('type', 'name')
    
    if request.method == 'POST':
        cat_id = request.POST.get('cat_id')
        name = request.POST.get('name')
        c_type = request.POST.get('type')
        icon = request.POST.get('icon', 'bi-tags-fill')
        color = request.POST.get('color', 'secondary')
        # print("Received POST data - cat_id:", cat_id, "name:", name, "type:", c_type, "icon:", icon, "color:", color)

        if cat_id:
            print("Editing category:", cat_id)
            # --- แก้ไข (Edit Mode) ---
            category = get_object_or_404(Category, id=cat_id, user=request.user)
            category.name = name
            category.type = c_type
            category.icon = icon
            category.color = color
            category.save()
            messages.success(request, "อัปเดตหมวดหมู่เรียบร้อย!")
        else:
            # --- เพิ่มใหม่ (Add Mode) ---
            Category.objects.create(
                user=request.user,
                name=name,
                type=c_type,
                icon=icon,
                color=color,
                is_global=False
            )
            messages.success(request, "เพิ่มหมวดหมู่ใหม่สำเร็จ!")
        
        return redirect('manage_categories')

    return render(request, 'expenses/manage_categories.html', {'categories': categories})



@login_required
def edit_category(request, cat_id):
    category = get_object_or_404(Category, id=cat_id)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "แก้ไขหมวดหมู่เรียบร้อย!")
            return redirect('manage_categories')
    return redirect('manage_categories')

@login_required
def delete_category(request, cat_id):
    category = get_object_or_404(Category, pk=cat_id)

    if category.is_global and category.name == "อื่นๆ":
        messages.error(request, "ไม่สามารถลบหมวดหมู่ 'อื่นๆ' ได้ เนื่องจากเป็นหมวดหมู่พื้นฐานของระบบ")
        return redirect('keyword_manager')
    

    if category.is_global:
        category.delete()
        messages.success(request, "ลบหมวดหมู่สากลเรียบร้อย")
        return redirect('keyword_manager')
    
    
    if category.user == request.user:
        category.delete()
        messages.success(request, "ลบหมวดหมู่เรียบร้อย")
    else:
        messages.error(request, "คุณไม่มีสิทธิ์ลบหมวดหมู่นี้")

    return redirect('manage_categories') # หรือหน้าที่คุณต้องการ

@login_required
def manage_budget(request):
    current_month = datetime.now().month
    current_year = datetime.now().year

    categories = Category.objects.filter(type='EXPENSE')
    budgets = Budget.objects.filter(month=current_month, year=current_year)
    
    budget_data = []
    for cat in categories:
        budget = budgets.filter(category=cat).first()
        limit = budget.amount_limit if budget else 0
        
        used = Transaction.objects.filter(
            category=cat, 
            date__month=current_month, 
            date__year=current_year,
            amount__lt=0
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        used = abs(used)
        percent = (used / limit * 100) if limit > 0 else 0
        remain = limit - used
        
        status_color = 'success'
        if percent >= 100: status_color = 'danger'
        elif percent >= 80: status_color = 'warning'

        budget_data.append({
            'category': cat,
            'limit': limit,
            'used': used,
            'remain': remain,
            'percent': min(percent, 100),
            'status_color': status_color,
            'budget_id': budget.id if budget else None
        })

    if request.method == 'POST':
        form = BudgetForm(request.POST, user=request.user)
        if form.is_valid():
            budget_item = form.save(commit=False)
            budget_item.user = request.user if request.user.is_authenticated else None 
            budget_item.month = current_month
            budget_item.year = current_year
            
            existing_budget = Budget.objects.filter(
                category=budget_item.category,
                month=current_month,
                year=current_year
            ).first()

            if existing_budget:
                existing_budget.amount_limit = budget_item.amount_limit
                existing_budget.save()
            else:
                budget_item.save()
                
            messages.success(request, f"ตั้งงบหมวด {budget_item.category.name} เรียบร้อย!")
            return redirect('manage_budget')
    else:
        form = BudgetForm(user=request.user)

    return render(request, 'expenses/budget_list.html', {
        'budget_data': budget_data,
        'form': form,
        'current_month': current_month,
        'current_year': current_year
    })

@login_required
def edit_budget(request, budget_id):
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    
    if request.method == 'POST':
        form = BudgetForm(request.POST, instance=budget, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "แก้ไขงบประมาณเรียบร้อย!")
            return redirect('manage_budget')
    else:
        form = BudgetForm(instance=budget, user=request.user)
    
    return render(request, 'expenses/edit_budget.html', {'form': form, 'budget': budget})

@login_required
def delete_budget(request, budget_id):
    budget = get_object_or_404(Budget, id=budget_id)
    budget.delete()
    messages.success(request, "ลบงบประมาณเรียบร้อย!")
    return redirect('manage_budget')