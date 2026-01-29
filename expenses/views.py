import re
import json 
from datetime import datetime, timedelta
import pandas as pd
import io
import os
import tempfile
import csv
import calendar


from django.shortcuts import render, redirect, get_object_or_404  
# from django.dispatch import receiver
from django.http import HttpResponse

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required,user_passes_test

from django.db.models.functions import TruncDay, ExtractWeekDay
from django.db.models import Sum , Q

from django.core.files.storage import FileSystemStorage
from django.core.paginator import Paginator

from django.utils import timezone
from datetime import datetime, timedelta,date

from .models import Transaction, Category, Budget , TrainingData , CategoryKeyword 
from .forms import SmartInputForm, CategoryForm, BudgetForm , UploadFileForm , TransactionForm  , UserUpdateForm , ProfileImageForm
from .utils import predict_category_fuzzy


# from .services import ai_classifier

def is_admin(user):
    return user.is_superuser


@login_required
def profile(request):
    user = request.user
    
    # เตรียม Form ตั้งต้น (Unbound)
    u_form = UserUpdateForm(instance=user)
    img_form = ProfileImageForm(instance=user.profile)
    pass_form = PasswordChangeForm(user)

    if request.method == 'POST':
        
        # --- กรณี 1: แก้ไขรูปภาพ/สี ---
        if 'btn_update_image' in request.POST:
            img_form = ProfileImageForm(request.POST, request.FILES, instance=user.profile)
            if img_form.is_valid():
                profile_obj = img_form.save(commit=False)
                new_color = request.POST.get('avatar_color')
                
                # Logic: ถ้าเลือกสี และไม่อัปรูป -> ลบรูปเก่า
                if new_color and not request.FILES.get('profile_picture'):
                    profile_obj.profile_picture = None
                
                profile_obj.save()
                messages.success(request, 'อัปเดตรูปโปรไฟล์สำเร็จ!')
                return redirect('profile')

        # --- กรณี 2: แก้ไขข้อมูลส่วนตัว ---
        elif 'btn_update_info' in request.POST:
            u_form = UserUpdateForm(request.POST, instance=user)
            if u_form.is_valid():
                u_form.save()
                messages.success(request, 'อัปเดตข้อมูลส่วนตัวสำเร็จ!')
                return redirect('profile')

        # --- กรณี 3: เปลี่ยนรหัสผ่าน ---
        elif 'btn_change_password' in request.POST:
            pass_form = PasswordChangeForm(user, request.POST)
            if pass_form.is_valid():
                user = pass_form.save()
                # สำคัญ: บรรทัดนี้ช่วยให้เปลี่ยนรหัสแล้ว session ไม่หลุด (ยังล็อกอินอยู่)
                update_session_auth_hash(request, user) 
                messages.success(request, 'เปลี่ยนรหัสผ่านเรียบร้อยแล้ว!')
                return redirect('profile')
            else:
                messages.error(request, 'กรุณาตรวจสอบรหัสผ่านอีกครั้ง')

    context = {
        'u_form': u_form,
        'img_form': img_form,
        'pass_form': pass_form,
        'current_color': user.profile.avatar_color or get_random_color(user.id)
    }
    return render(request, 'expenses/profile.html', context)

# สุ่มสีโปรไฟล์
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
    # ==========================
    # 1. 🗑️ จัดการลบ (Bulk Delete)
    # ==========================
    if request.method == 'POST' and 'bulk_delete' in request.POST:
        # รับ ID ที่ถูกติ๊กเลือกมาเป็น list
        selected_ids = request.POST.getlist('selected_ids')
        if selected_ids:
            # ลบทีเดียวรวดเดียว
            deleted_count, _ = CategoryKeyword.objects.filter(id__in=selected_ids).delete()
            messages.success(request, f"ลบคำศัพท์เรียบร้อย {deleted_count} รายการ")
        else:
            messages.warning(request, "กรุณาเลือกรายการที่จะลบ")
        return redirect('keyword_manager')

    # ==========================
    # 2. 📂 จัดการ Import CSV
    # ==========================
    if request.method == 'POST' and 'import_csv' in request.POST and request.FILES.get('csv_file'):
        try:
            csv_file = request.FILES['csv_file']
            # อ่านไฟล์ CSV (รองรับภาษาไทย)
            decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
            reader = csv.reader(decoded_file)
            
            count = 0
            for row in reader:
                # ข้ามหัวตาราง หรือแถวว่าง
                if len(row) < 2 or "คำศัพท์" in row[0]: continue
                
                word = row[0].strip()
                cat_name = row[1].strip()
                
                if word and cat_name:
                    # หาหมวดหมู่ (ถ้าไม่มีก็ข้าม หรือจะสร้างใหม่ก็ได้)
                    cat = Category.objects.filter(name__iexact=cat_name).first()
                    if cat:
                        # update_or_create: ถ้ามีคำนี้แล้วให้อัปเดต ถ้าไม่มีให้สร้าง
                        obj, created = CategoryKeyword.objects.update_or_create(
                            word=word,
                            defaults={'category': cat}
                        )
                        count += 1
            
            messages.success(request, f"นำเข้า/อัปเดตคำศัพท์สำเร็จ {count} คำ!")
            return redirect('keyword_manager')

        except Exception as e:
            messages.error(request, f"เกิดข้อผิดพลาด: {e}")

    # ==========================
    # 3. 🔍 จัดการแสดงผล (Search & Filter)
    # ==========================
    keywords = CategoryKeyword.objects.all().order_by('category__name', 'word')

    # ค้นหา (Search)
    search_query = request.GET.get('q')
    if search_query:
        keywords = keywords.filter(word__icontains=search_query)

    # กรองหมวดหมู่ (Filter)
    cat_filter = request.GET.get('category')
    if cat_filter:
        keywords = keywords.filter(category__id=cat_filter)

    # แบ่งหน้า (Pagination) - หน้าละ 50 คำ
    paginator = Paginator(keywords, 50) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # ดึงรายชื่อหมวดหมู่ไปใส่ Dropdown Filter
    categories = Category.objects.filter(is_global=True).order_by('name')

    return render(request, 'expenses/keyword_manager.html', {
        'page_obj': page_obj,
        'categories': categories,
        'search_query': search_query,
        'current_cat': cat_filter
    })

def add_keyword(request):
    if request.method == "POST":
        word_text = request.POST.get('word_text')
        category_id = request.POST.get('category_id')

        if word_text and category_id:
            try:
                # ดึงหมวดหมู่ตาม ID
                category_obj = Category.objects.get(id=category_id)
                
                # สร้าง Keyword ใหม่ (ใช้ get_or_create เพื่อป้องกัน Error ถ้าคำซ้ำเพราะ unique=True)
                keyword, created = CategoryKeyword.objects.get_or_create(
                    word=word_text,
                    defaults={'category': category_obj}
                )

                if created:
                    messages.success(request, f'เพิ่มคำว่า "{word_text}" สำเร็จ!')
                else:
                    # ถ้าคำนี้มีอยู่แล้ว อัปเดตหมวดหมู่ใหม่ให้เลย
                    keyword.category = category_obj
                    keyword.save()
                    messages.info(request, f'อัปเดตหมวดหมู่ของคำว่า "{word_text}" เรียบร้อย')

            except Exception as e:
                messages.error(request, f'เกิดข้อผิดพลาด: {e}')
        
        return redirect('dashboard') # เปลี่ยน 'dashboard' เป็นชื่อ url หน้าที่คุณอยู่

    # ถ้าไม่ใช่ POST เด้งกลับไปหน้าหลัก
    return redirect('dashboard')


# ไม่ได้ใช้แล้ว เพราะย้ายไปใช้ fuzzy logic แทน
@user_passes_test(is_admin)
def ai_manager(request):
    # 1. จัดการ Re-train
    if request.method == 'POST' and 'retrain' in request.POST:
        ai_classifier.train_model()
        messages.success(request, "Re-train Model เรียบร้อยแล้ว!")
        return redirect('ai_manager')

    # 2. จัดการ Import CSV Training Data
    if request.method == 'POST' and 'import_csv' in request.POST and request.FILES['csv_file']:
        try:
            csv_file = request.FILES['csv_file']
            
            # ใช้ utf-8-sig เพื่อรองรับไฟล์จาก Excel/Notepad ที่มี BOM
            decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
            reader = csv.reader(decoded_file)
            
            count = 0
            created_cats = 0
            
            for row in reader:
                # ข้ามบรรทัดหัวตาราง (ถ้าบรรทัดแรกคือคำว่า "คำศัพท์")
                if len(row) >= 1 and "คำศัพท์" in row[0]:
                    continue

                if len(row) >= 2:
                    text = row[0].strip()
                    cat_name = row[1].strip()
                    
                    if not text or not cat_name: continue

                    # 1. หาหมวดหมู่ (ถ้าไม่มี ให้สร้างใหม่เลย!)
                    cat = Category.objects.filter(name__iexact=cat_name).first()
                    if not cat:
                        # สร้างหมวดหมู่ใหม่ (Default ให้เป็นรายจ่ายไว้ก่อน)
                        cat = Category.objects.create(
                            name=cat_name, 
                            type='EXPENSE', 
                            is_global=True # ให้เป็น Global ไปเลยเพราะ Admin นำเข้า
                        )
                        created_cats += 1

                    # 2. บันทึกลง Training Data (ถ้ายังไม่มีคำนี้)
                    obj, created = TrainingData.objects.get_or_create(
                        text=text,
                        category=cat,
                        defaults={'is_verified': True}
                    )
                    if created:
                        count += 1
            
            # Import เสร็จแล้ว Re-train ทันที
            ai_classifier.train_model()
            
            msg = f"นำเข้าศัพท์ใหม่ {count} คำ"
            if created_cats > 0:
                msg += f" และสร้างหมวดหมู่ใหม่ {created_cats} หมวด"
            
            messages.success(request, msg + " เรียบร้อย!")
            
        except Exception as e:
            messages.error(request, f"เกิดข้อผิดพลาด: {e}")
            
        return redirect('ai_manager')

    # แสดงข้อมูล Training Data ล่าสุด 20 รายการ
    training_data = TrainingData.objects.all().order_by('-created_at')[:20]
    
    return render(request, 'expenses/ai_manager.html', {'training_data': training_data})

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
    
    if request.method == 'POST':
        if 'confirm_save' in request.POST:
            try:
                json_data = request.POST.get('final_data')
                try:
                    data_list = json.loads(json_data)
                    if isinstance(data_list, str): data_list = json.loads(data_list)
                except (ValueError, TypeError): data_list = []

                txns = []
                for item in data_list:
                    if isinstance(item, str):
                        try: item = json.loads(item)
                        except: continue
                    
                    try: date_obj = datetime.strptime(item.get('date', ''), '%Y-%m-%d').date()
                    except: date_obj = datetime.now().date()
                    
                    cat_obj = None
                    if item.get('category_id'):
                        cat_obj = Category.objects.filter(id=item['category_id']).first()
                    
                    txns.append(Transaction(
                        user=request.user,
                        description=item.get('description', ''),
                        amount=float(item.get('amount', 0)),
                        date=date_obj,
                        category=cat_obj
                    ))
                
                if txns:
                    Transaction.objects.bulk_create(txns)
                    messages.success(request, f"บันทึกสำเร็จ {len(txns)} รายการ!")
                    return redirect('dashboard')
            except Exception as e:
                messages.error(request, f"เกิดข้อผิดพลาดในการบันทึก: {e}")

        else:
            form = SmartInputForm(request.POST)
            if form.is_valid():
                raw_data = form.cleaned_data['raw_data']
                lines = raw_data.strip().split('\n')
                preview_list = []
                current_date = datetime.now().date()

                for line in lines:
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
                            
                            # ลบวันที่ออกจาก text เพื่อไม่ให้ไปกวนชื่อรายการ
                            line = line.replace(date_match.group(0), '').strip()
                        except ValueError:
                            pass # ถ้าวันที่พัง ใช้วันปัจจุบัน

                    description = "รายการทั่วไป"
                    final_amount = 0.0

                    # Regex สำหรับตัวเลข (รองรับ , และทศนิยม)
                    num_re = r'([+-]?[0-9,]+(?:\.\d+)?)'

                    # CASE A: เงินนำหน้า (เช่น "-100 7-11" หรือ "500 เงินเดือน")
                    # ^ = เริ่มต้นบรรทัด, \s+ = เว้นวรรค
                    match_front = re.match(r'^' + num_re + r'\s+(.*)$', line)

                    # CASE B: เงินปิดท้าย (เช่น "7-11 -100" หรือ "ค่าข้าว 50")
                    # $ = จบบรรทัด
                    match_back = re.match(r'^(.*)\s+' + num_re + r'$', line)

                    if match_front:
                        # เจอยอดเงินข้างหน้า
                        amount_str = match_front.group(1)
                        description = match_front.group(2).strip()
                    elif match_back:
                        # เจอยอดเงินข้างหลัง
                        description = match_back.group(1).strip()
                        amount_str = match_back.group(2)
                    else:
                        # CASE C: กรณี User พิมพ์แต่ตัวเลขมา (ไม่มีชื่อ)
                        try:
                            # ลองแปลงทั้งบรรทัดดูว่าเป็นตัวเลขไหม
                            test_amt = float(line.replace(',', ''))
                            amount_str = line
                            description = "รายการทั่วไป" # ตั้งชื่อ default ให้
                        except ValueError:
                            continue # ถ้าไม่ใช่ตัวเลขเลย และแยกไม่ออก ข้ามบรรทัดนี้

                    # แปลงยอดเงินเป็น float
                    try:
                        amount_val = float(amount_str.replace(',', ''))
                        
                        # Logic เดิมของคุณ: ถ้ามีเครื่องหมายลบใน string ให้เป็นลบ, ถ้าไม่มีเป็นบวก
                        # แต่ระวัง: ถ้า user พิมพ์ "7-11 100" (ไม่มีลบ) มันจะเป็นรายรับ
                        # ถ้าคุณอยากให้ Default เป็นรายจ่าย ต้องแก้ logic ตรงนี้
                        if '-' in amount_str:
                            final_amount = -abs(amount_val)
                        else:
                            final_amount = abs(amount_val)
                            
                    except ValueError:
                        continue

                    category_id = ""
                    category_name = "-"
                    
                    # 1. เช็คจากประวัติเดิม (Exact Match)
                    prev = Transaction.objects.filter(user=request.user, description__iexact=description).order_by('-created_at').first()
                    if prev and prev.category:
                        category_id = prev.category.id
                        category_name = prev.category.name
                    
                    # 2. ถ้าไม่มีประวัติเดิม -> ใช้ Fuzzy Logic + Database
                    if not category_id:
                        # ✅ เรียกใช้ Fuzzy Logic แทน AI ตัวเก่า
                        predicted_cat, matched_word, score = predict_category_fuzzy(description)
                        print("score:", score)
                        if predicted_cat:
                            category_id = predicted_cat.id
                            # แสดงคำที่จับคู่ได้ เพื่อให้ User รู้ว่าทำไมถึงเลือกหมวดนี้
                            category_name = f"{predicted_cat.name} (Auto)" 

                    preview_list.append({
                        'date': current_date.strftime('%Y-%m-%d'),
                        'description': description,
                        'amount': final_amount,
                        'category_id': category_id,
                        'category_name': category_name
                    })
                    
                preview_data = preview_list 

    income_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='INCOME').order_by('name')
    expense_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='EXPENSE').order_by('name')

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
                    if item.get('category_id'):
                        cat_obj = Category.objects.filter(id=item['category_id']).first()
                    
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

                                # 1. เช็คว่าในไฟล์ระบุหมวดหมู่มาไหม
                                if 'category' in df.columns and pd.notna(row['category']):
                                    cat_name_str = str(row['category']).strip()
                                    c = Category.objects.filter(name__iexact=cat_name_str).first()
                                    if c: 
                                        cat_id = c.id
                                        cat_name = c.name
                                
                                # 2. ถ้าไม่มี ให้เช็คประวัติเก่า
                                if not cat_id:
                                    prev = Transaction.objects.filter(user=request.user, description__iexact=description).order_by('-created_at').first()
                                    if prev and prev.category:
                                        cat_id = prev.category.id
                                        cat_name = prev.category.name

                                # 3. ถ้าไม่มีประวัติ -> ใช้ Fuzzy Logic + Database
                                if not cat_id:
                                    # ✅ เรียกใช้ Fuzzy Logic แทน AI ตัวเก่า
                                    predicted_cat, matched_word, score = predict_category_fuzzy(description)
                                    
                                    if predicted_cat:
                                        cat_id = predicted_cat.id
                                        cat_name = f"{predicted_cat.name} (Auto)"

                                preview_list.append({
                                    'date': txn_date.strftime('%Y-%m-%d'),
                                    'description': description,
                                    'amount': amt,
                                    'category_id': cat_id,
                                    'category_name': cat_name
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
    # ==========================================
    # 1. 🕒 จัดการวันที่ (Reference Date System)
    # ==========================================
    today = timezone.now().date()
    
    # รับค่าวันที่จาก URL (ถ้าไม่มี ให้ใช้วันนี้)
    date_str = request.GET.get('date')
    if date_str:
        try:
            ref_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            ref_date = today
    else:
        ref_date = today

    # --- คำนวณขอบเขตของ "เดือน" (สำหรับกราฟซ้าย) ---
    curr_month = ref_date.month
    curr_year = ref_date.year
    days_in_month = calendar.monthrange(curr_year, curr_month)[1]
    
    month_start = date(curr_year, curr_month, 1)
    month_end = date(curr_year, curr_month, days_in_month)

    # --- คำนวณขอบเขตของ "สัปดาห์" (สำหรับกราฟขวา) ---
    # หาว่า ref_date ตรงกับวันอะไร (0=จันทร์, 6=อาทิตย์)
    weekday = ref_date.weekday() 
    # หาวันจันทร์ของสัปดาห์นี้
    week_start = ref_date - timedelta(days=weekday)
    # หาวันอาทิตย์ของสัปดาห์นี้
    week_end = week_start + timedelta(days=6)

    # ==========================================
    # 2. 🎮 สร้างปุ่ม Navigator (Logic หัวใจสำคัญ)
    # ==========================================
    
    # A. ปุ่มเลื่อนสัปดาห์ (+/- 7 วัน)
    prev_week_date = ref_date - timedelta(days=7)
    next_week_date = ref_date + timedelta(days=7)


    # B. ปุ่มเลื่อนเดือน (Jump Logic)
    # --------------------------------------------------------
    # เป้าหมายเบื้องต้น (Naive Targets)
    # ถอยหลัง: ไปวันสุดท้ายของเดือนก่อน
    naive_prev_target = month_start - timedelta(days=1)
    # เดินหน้า: ไปวันแรกของเดือนหน้า
    naive_next_target = month_end + timedelta(days=1)

    # --- 🧠 Smart Jump Logic: เช็คว่าซ้ำสัปดาห์เดิมไหม ---
    
    # 1. เช็คเดือนถัดไป (Next Month)
    # หาวันจันทร์ของเป้าหมายเดือนหน้า
    next_target_weekday = naive_next_target.weekday()
    next_target_week_start = naive_next_target - timedelta(days=next_target_weekday)

    # ถ้าเป้าหมายเดือนหน้า ดันอยู่ในสัปดาห์เดียวกับที่เราดูอยู่ (week_start ปัจจุบัน)
    if next_target_week_start == week_start:
        # ให้บวกเพิ่มไปอีก 7 วัน (กระโดดไปสัปดาห์ที่ 2 ของเดือนใหม่เลย)
        next_month_target = naive_next_target + timedelta(days=7)
    else:
        # ถ้าไม่ซ้ำ ก็ไปวันแรกของเดือนตามปกติ
        next_month_target = naive_next_target

    # 2. เช็คเดือนก่อนหน้า (Prev Month)
    # หาวันจันทร์ของเป้าหมายเดือนก่อน
    prev_target_weekday = naive_prev_target.weekday()
    prev_target_week_start = naive_prev_target - timedelta(days=prev_target_weekday)

    # ถ้าเป้าหมายเดือนก่อน ดันอยู่ในสัปดาห์เดียวกับที่เราดูอยู่
    if prev_target_week_start == week_start:
        # ให้ถอยหลังไปอีก 7 วัน (กระโดดไปสัปดาห์ก่อนหน้าของเดือนเก่า)
        prev_month_target = naive_prev_target - timedelta(days=7)
    else:
        prev_month_target = naive_prev_target

    # ชื่อเดือนไทย
    thai_months = [
        "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ]
    current_month_name = thai_months[curr_month]

    # ==========================================
    # 3. 💰 ดึงข้อมูล (Query)
    # ==========================================
    
    # 3.1 ข้อมูลทั้งเดือน (ใช้คำนวณยอดรวม และ กราฟซ้าย)
    monthly_txns = Transaction.objects.filter(
        user=request.user, 
        date__range=[month_start, month_end]
    ).order_by('-date', '-created_at')

    # ยอดรวมการ์ด 3 ใบ (คิดจากทั้งเดือน)
    total_income = float(monthly_txns.filter(amount__gt=0).aggregate(Sum('amount'))['amount__sum'] or 0)
    total_expense = float(monthly_txns.filter(amount__lt=0).aggregate(Sum('amount'))['amount__sum'] or 0)
    balance = total_income + total_expense

    # Top 3 ของเดือน (ใช้กับกราฟซ้าย)
    top_3_cats = monthly_txns.filter(amount__lt=0).values('category__name').annotate(total=Sum('amount')).order_by('total')[:3]
    top_3_names = [item['category__name'] for item in top_3_cats]

    # 3.2 ข้อมูลเฉพาะสัปดาห์ (ใช้กับกราฟขวา)
    weekly_txns = Transaction.objects.filter(
        user=request.user,
        date__range=[week_start, week_end],
        amount__lt=0 # เอาเฉพาะรายจ่ายมาพลอตกราฟ
    )

    # ==========================================
    # 4. 📈 เตรียมข้อมูลกราฟ (Chart Data)
    # ==========================================

    # --- Chart 1: Monthly Forecast (กราฟซ้าย - รายเดือน) ---
    all_days_labels = [str(i) for i in range(1, days_in_month + 1)]
    line_datasets = []
    
    is_current_month_real = (curr_year == today.year) and (curr_month == today.month)

    for cat_name in top_3_names:
        display_name = cat_name if cat_name else "ไม่ระบุ"
        
        # ดึงรายจ่ายรายวันของหมวดนี้ (ทั้งเดือน)
        daily_cat_expenses = monthly_txns.filter(
            amount__lt=0, category__name=cat_name
        ).annotate(day=TruncDay('date')).values('day').annotate(total=Sum('amount')).order_by('day')
        
        daily_map = {item['day'].day: float(abs(item['total'])) for item in daily_cat_expenses}
        
        cumulative_data = []
        current_sum = 0.0
        
        # เส้น Actual
        for day in range(1, days_in_month + 1):
            # ถ้าเป็นเดือนปัจจุบัน โชว์ถึงวันนี้ / ถ้าเดือนอื่น โชว์หมด
            if not is_current_month_real or (is_current_month_real and day <= today.day):
                amount = daily_map.get(day, 0.0)
                current_sum += amount
                cumulative_data.append(current_sum)
            else:
                break
        
        line_datasets.append({
            'label': display_name, 'data': cumulative_data, 'mode': 'actual'
        })

        # เส้น Forecast (เฉพาะเดือนปัจจุบัน)
        if is_current_month_real and today.day > 0 and current_sum > 0:
            avg_burn_rate = current_sum / today.day
            forecast_list = [None] * (today.day - 1)
            forecast_list.append(current_sum)
            val = current_sum
            for _ in range(today.day + 1, days_in_month + 1):
                val += avg_burn_rate
                forecast_list.append(val)
            
            line_datasets.append({
                'label': f'{display_name} (คาดการณ์)', 'data': forecast_list, 'mode': 'forecast'
            })

    # --- Chart 2: Weekly Behavior (กราฟขวา - รายสัปดาห์เจาะจง) ---
    # เราต้องพลอต 7 วัน (จันทร์-อาทิตย์) ของสัปดาห์ที่เลือก
    weekly_labels_th = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัส', 'ศุกร์', 'เสาร์', 'อาทิตย์']
    
    # รวมยอดตามวันในสัปดาห์ (เฉพาะ Transaction ในช่วง week_start ถึง week_end)
    weekly_agg = weekly_txns.annotate(weekday=ExtractWeekDay('date')).values('weekday', 'category__name').annotate(total=Sum('amount'))
    
    # Django ExtractWeekDay: 1=อาทิตย์, 2=จันทร์, ..., 7=เสาร์
    # เราต้องแปลงเป็น index 0-6 (0=จันทร์, ..., 6=อาทิตย์) ให้ตรงกับ Chart
    # Map: Sun(1)->6, Mon(2)->0, Tue(3)->1 ... Sat(7)->5
    def django_weekday_to_idx(w):
        return (w - 2) % 7

    stacked_datasets = []
    
    # ใช้ Top 3 หมวดเดิม (เพื่อให้สีเหมือนกราฟซ้าย)
    for cat_name in top_3_names:
        display_name = cat_name if cat_name else "ไม่ระบุ"
        data_points = [0.0] * 7
        for item in weekly_agg:
            if item['category__name'] == cat_name:
                idx = django_weekday_to_idx(item['weekday'])
                data_points[idx] += float(abs(item['total']))
        
        stacked_datasets.append({'label': display_name, 'data': data_points})

    # หมวดอื่นๆ
    others_data_points = [0.0] * 7
    for item in weekly_agg:
        if item['category__name'] not in top_3_names:
            idx = django_weekday_to_idx(item['weekday'])
            others_data_points[idx] += float(abs(item['total']))
    
    if any(others_data_points):
        stacked_datasets.append({'label': 'อื่นๆ', 'data': others_data_points, 'backgroundColor': '#d1d3e2'})

    advisor_msg = f"ภาพรวมเดือน {current_month_name} (สัปดาห์ที่ {week_start.day}-{week_end.day})"

    context = {
        'transactions': monthly_txns, # รายการโชว์ทั้งเดือนเหมือนเดิม
        'total_income': total_income,
        'total_expense': abs(total_expense),
        'balance': balance,
        
        # กราฟ
        'forecast_labels': json.dumps(all_days_labels),
        'line_datasets': json.dumps(line_datasets),
        'weekly_labels': json.dumps(weekly_labels_th),
        'stacked_datasets': json.dumps(stacked_datasets),
        'advisor_msg': advisor_msg,

        # Navigator Variables
        'current_month_name': current_month_name,
        'current_year': curr_year + 543,
        'week_range_str': f"{week_start.day} {thai_months[week_start.month]} - {week_end.day} {thai_months[week_end.month]}",
        
        # Link URLs
        'prev_month_url': f"?date={prev_month_target}",
        'next_month_url': f"?date={next_month_target}",
        'prev_week_url': f"?date={prev_week_date}",
        'next_week_url': f"?date={next_week_date}",
    }

    return render(request, 'expenses/dashboard.html', context)


@login_required
def transaction_list(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-date', '-created_at')
    
    # ดึงหมวดหมู่แยกประเภท ส่งไปให้ Dropdown ใน Modal
    income_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='INCOME').order_by('name')
    expense_cats = Category.objects.filter(Q(is_global=True) | Q(user=request.user), type='EXPENSE').order_by('name')

    context = {
        'transactions': transactions,
        'income_cats': income_cats,
        'expense_cats': expense_cats
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
    
    return render(request, 'expenses/edit_transaction.html', {'form': form, 'transaction': transaction})


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
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user if request.user.is_authenticated else None
            category.is_global = False 
            category.save()
            messages.success(request, "เพิ่มหมวดหมู่สำเร็จ!")
            return redirect('manage_categories')
    else:
        form = CategoryForm()

    return render(request, 'expenses/category_list.html', {'categories': categories, 'form': form})

@login_required
def edit_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "แก้ไขหมวดหมู่เรียบร้อย!")
            return redirect('manage_categories')
    return redirect('manage_categories')

@login_required
def delete_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category.delete()
    messages.success(request, "ลบหมวดหมู่เรียบร้อย!")
    return redirect('manage_categories')

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