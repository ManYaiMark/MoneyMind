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
from .utils import predict_category_fuzzy, parse_smart_transactions, process_uploaded_file
from .services import get_dashboard_context
from allauth.account.views import PasswordResetView

# from .services import ai_classifier

def is_admin(user):
    return user.is_superuser

User = get_user_model()

def get_random_color(user_id):
    colors = ['bg-primary', 'bg-success', 'bg-danger', 'bg-dark', 'bg-secondary', 'bg-info']
    return colors[user_id % len(colors)]

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
    total_system_txns = Transaction.objects.count()

    categories = Category.objects.filter(is_global=True).annotate(
        txn_count=Count('transaction')
    ).prefetch_related('categorykeyword_set').order_by('type', 'name')

    for cat in categories:
        keywords = [k.word for k in cat.categorykeyword_set.all()]
        cat.keyword_list = keywords
        cat.keyword_list_str = ",".join(keywords)

        if total_system_txns > 0:
            percent = (cat.txn_count / total_system_txns) * 100
            cat.usage_percent = round(percent, 1)
        else:
            cat.usage_percent = 0

    expense_cats = [c for c in categories if c.type == 'EXPENSE']
    income_cats = [c for c in categories if c.type == 'INCOME']
    
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
        cat_id = request.POST.get('cat_id')
        name = request.POST.get('name').strip()
        cat_type = request.POST.get('type')
        keywords_str = request.POST.get('keywords_list', '')

        if not name:
            messages.error(request, "กรุณาระบุชื่อหมวดหมู่")
            return redirect('keyword_manager')

        try:
            if cat_id:
                category = get_object_or_404(Category, id=cat_id)
                category.name = name
                category.type = cat_type
                category.save()
                action_msg = "อัปเดต"
            else:
                if Category.objects.filter(name__iexact=name, is_global=True).exists():
                    messages.warning(request, f"หมวดหมู่ '{name}' มีอยู่ในระบบแล้ว")
                    return redirect('keyword_manager')
                
                category = Category.objects.create(
                    name=name,
                    type=cat_type,
                    is_global=True,
                    user=None
                )
                action_msg = "สร้าง"

            new_keywords_list = [k.strip() for k in keywords_str.split(',') if k.strip()]
            current_keywords = list(CategoryKeyword.objects.filter(category=category).values_list('word', flat=True))

            to_add = set(new_keywords_list) - set(current_keywords)
            to_remove = set(current_keywords) - set(new_keywords_list)

            if to_add:
                CategoryKeyword.objects.bulk_create([
                    CategoryKeyword(word=word, category=category) for word in to_add
                ])

            if to_remove:
                CategoryKeyword.objects.filter(category=category, word__in=to_remove).delete()

            messages.success(request, f"{action_msg}หมวดหมู่ '{name}' และบันทึกคำศัพท์เรียบร้อยแล้ว")

        except Exception as e:
            messages.error(request, f"เกิดข้อผิดพลาด: {e}")
        
        return redirect('keyword_manager')

    return redirect('keyword_manager')

@user_passes_test(is_admin)
def admin_user_list(request):
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
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        has_google = SocialAccount.objects.filter(user=user, provider='google').exists()
        
        if not has_google:
            user.username = request.POST.get('username')
            user.email = request.POST.get('email')
            
        user.is_active = 'is_active' in request.POST
        user.is_staff = 'is_staff' in request.POST

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
    target_user = get_object_or_404(User, id=user_id)
    
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
    if u != request.user:
        u.delete()
        messages.success(request, f"ลบผู้ใช้ {u.username} ออกจากระบบถาวรแล้ว")
    return redirect('admin_user_list')


@login_required
def add_smart_transaction(request):
    preview_data = None
    form = SmartInputForm()
    
    income_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='INCOME').order_by('name')
    expense_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='EXPENSE').order_by('name')

    if request.method == 'POST':
        if 'confirm_save' in request.POST:
            try:
                json_data = request.POST.get('final_data')
                try:
                    data_list = json.loads(json_data)
                    if isinstance(data_list, str): 
                        data_list = json.loads(data_list)
                except (ValueError, TypeError): 
                    data_list = []

                txns = []
                for item in data_list:
                    if isinstance(item, str):
                        try: item = json.loads(item)
                        except: continue
                    
                    try: 
                        date_obj = datetime.strptime(item.get('date', ''), '%Y-%m-%d').date()
                    except: 
                        date_obj = datetime.now().date()
                    
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
                    messages.success(request, f"✅ บันทึกสำเร็จ {len(txns)} รายการ!")
                    return redirect('dashboard')
                else:
                    messages.warning(request, "ไม่มีข้อมูลให้บันทึก")

            except Exception as e:
                messages.error(request, f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}")

        else:
            form = SmartInputForm(request.POST)
            if form.is_valid():
                raw_data = form.cleaned_data['raw_data']
                preview_data = parse_smart_transactions(raw_data, request.user)

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
                preview_list, messages_list = process_uploaded_file(file, request.user)
                for msg_type, msg_text in messages_list:
                    if msg_type == 'error': messages.error(request, msg_text)
                    elif msg_type == 'warning': messages.warning(request, msg_text)
                if preview_list: preview_data = preview_list
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

    context = get_dashboard_context(request.user, request.GET.get('date'))
    return render(request, 'expenses/dashboard.html', context)


@login_required
def transaction_list(request):
    transactions = Transaction.objects.filter(user=request.user)
    total_count = transactions.count()

    active_dates = list(transactions.values_list('date', flat=True).distinct())
    active_dates_json = json.dumps([d.strftime('%Y-%m-%d') for d in active_dates])

    query = request.GET.get('q', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    category_id = request.GET.get('category', '')

    if query:
        transactions = transactions.filter(description__icontains=query)
    if start_date and end_date:
        transactions = transactions.filter(date__range=[start_date, end_date])
    if category_id:
        transactions = transactions.filter(category_id=category_id)

    transactions = transactions.order_by('-date', '-created_at')
    
    income_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='INCOME').order_by('name')
    expense_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='EXPENSE').order_by('name')
    
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
            old_category = transaction.category 
            updated_txn = form.save()
            
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

        if cat_id:
            # print("Editing category:", cat_id)
            #แก้ไข 
            category = get_object_or_404(Category, id=cat_id, user=request.user)
            category.name = name
            category.type = c_type
            category.icon = icon
            category.color = color
            category.save()
            messages.success(request, "อัปเดตหมวดหมู่เรียบร้อย!")
        else:
            # เพิ่ม
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



# @login_required
# def edit_category(request, cat_id):
#     category = get_object_or_404(Category, id=cat_id)
#     if request.method == 'POST':
#         form = CategoryForm(request.POST, instance=category)
#         if form.is_valid():
#             form.save()
#             messages.success(request, "แก้ไขหมวดหมู่เรียบร้อย!")
#             return redirect('manage_categories')
#     return redirect('manage_categories')

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
        messages.success(request, "ลบหมวดหมู่ส่วนตัวเรียบร้อย")
    else:
        messages.error(request, "คุณไม่มีสิทธิ์ลบหมวดหมู่นี้")

    return redirect('manage_categories')


@login_required
def manage_budget(request):
    current_month = datetime.now().month
    current_year = datetime.now().year

    categories = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='EXPENSE')
    budgets = Budget.objects.filter(user=request.user, month=current_month, year=current_year)
    
    budget_data = []
    for cat in categories:
        budget = budgets.filter(category=cat).first()
        limit = budget.amount_limit if budget else 0
        
        used = Transaction.objects.filter(
            user=request.user,
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
                user=request.user,
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
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    budget.delete()
    messages.success(request, "ลบงบประมาณเรียบร้อย!")
    return redirect('manage_budget')