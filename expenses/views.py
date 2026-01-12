import re
import json 
from datetime import datetime, timedelta
import pandas as pd
import io
import os
import tempfile
import csv


from django.db.models import Sum , Q
from django.shortcuts import render, redirect, get_object_or_404  
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.core.files.storage import FileSystemStorage

from .models import Transaction, Category, Budget , TrainingData
from .forms import SmartInputForm, CategoryForm, BudgetForm , UploadFileForm , TransactionForm  



from .services import ai_classifier

def is_admin(user):
    return user.is_superuser


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

                    date_match = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})', line)
                    if date_match and len(line) <= 10:
                        day, month, year = map(int, date_match.groups())
                        if year < 100: year += 2000
                        try: current_date = datetime(year, month, day).date()
                        except ValueError: pass
                        continue

                    # ✅ แก้ไข 1: Regex รองรับลูกน้ำ [0-9,]+
                    amount_match = re.search(r'([+-]?[0-9,]+(\.\d+)?)', line)
                    if amount_match:
                        amount_str = amount_match.group(1)
                        try:
                            # ✅ แก้ไข 2: ลบลูกน้ำออกก่อนแปลงเป็น float
                            amount_val = float(amount_str.replace(',', ''))
                        except ValueError: continue
                        
                        if '-' in amount_str: final_amount = -abs(amount_val)
                        else: final_amount = abs(amount_val)

                        description = line.replace(amount_str, '').strip()
                        if date_match: description = description.replace(date_match.group(0), '').strip()
                        if not description: description = "รายการทั่วไป"

                        category_id = ""
                        category_name = "-"
                        
                        prev = Transaction.objects.filter(user=request.user, description__iexact=description).order_by('-created_at').first()
                        if prev and prev.category:
                            category_id = prev.category.id
                            category_name = prev.category.name
                        
                        if not category_id:
                            try:
                                predicted_cat, prob = ai_classifier.predict(description)
                                if predicted_cat and prob > 0.4:
                                    category_id = predicted_cat.id
                                    category_name = f"{predicted_cat.name} (AI)"
                            except: pass

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
                                
                                date_match = re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$', line)
                                if date_match:
                                    d, m, y = map(int, date_match.groups())
                                    if y < 100: y += 2000
                                    try: current_date = datetime(y, m, d).date()
                                    except ValueError: pass
                                    continue 
                                
                                # ✅ แก้ไข 1: Regex รองรับลูกน้ำ
                                amount_match = re.search(r'([+-]?[0-9,]+(\.\d+)?)', line)
                                if amount_match:
                                    amt_str = amount_match.group(1)
                                    try:
                                        # ✅ แก้ไข 2: ลบลูกน้ำก่อนแปลงค่า
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
                                # จัดการลูกน้ำใน Excel ด้วย (เผื่อ Excel ส่งมาเป็น String ที่มี ,)
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

                                if 'category' in df.columns and pd.notna(row['category']):
                                    cat_name_str = str(row['category']).strip()
                                    c = Category.objects.filter(name__iexact=cat_name_str).first()
                                    if c: 
                                        cat_id = c.id
                                        cat_name = c.name
                                
                                if not cat_id:
                                    prev = Transaction.objects.filter(user=request.user, description__iexact=description).order_by('-created_at').first()
                                    if prev and prev.category:
                                        cat_id = prev.category.id
                                        cat_name = prev.category.name

                                if not cat_id:
                                    try:
                                        predicted_cat, prob = ai_classifier.predict(description)
                                        if predicted_cat and prob > 0.4:
                                            cat_id = predicted_cat.id
                                            cat_name = f"{predicted_cat.name} (AI)"
                                    except: pass

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
def dashboard(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-date', '-created_at')

    total_income = transactions.filter(amount__gt=0).aggregate(Sum('amount'))['amount__sum'] or 0
    total_expense = transactions.filter(amount__lt=0).aggregate(Sum('amount'))['amount__sum'] or 0
    balance = total_income + total_expense

    expense_by_cat = transactions.filter(amount__lt=0).values('category__name').annotate(total=Sum('amount')).order_by('total')
    
    donut_labels = []
    donut_data = []
    for item in expense_by_cat:
        cat_name = item['category__name'] if item['category__name'] else 'ไม่ระบุหมวด'
        donut_labels.append(cat_name)
        donut_data.append(abs(float(item['total'])))

    today = datetime.now().date()
    last_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    
    bar_labels = []
    bar_income = []
    bar_expense = []

    for day in last_7_days:
        bar_labels.append(day.strftime('%d/%m'))
        day_txns = transactions.filter(date=day)
        inc = day_txns.filter(amount__gt=0).aggregate(Sum('amount'))['amount__sum'] or 0
        exp = day_txns.filter(amount__lt=0).aggregate(Sum('amount'))['amount__sum'] or 0
        bar_income.append(float(inc))
        bar_expense.append(abs(float(exp)))

    context = {
        'transactions': transactions[:5],
        'total_income': total_income,
        'total_expense': abs(total_expense),
        'balance': balance,
        'donut_labels': json.dumps(donut_labels),
        'donut_data': json.dumps(donut_data),
        'bar_labels': json.dumps(bar_labels),
        'bar_income': json.dumps(bar_income),
        'bar_expense': json.dumps(bar_expense),
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
            # ถ้ามีการเปลี่ยนหมวดหมู่ หรือ รายการเดิมไม่มีหมวดหมู่
            if updated_txn.category != old_category:
                # สั่งให้ AI จำคำนี้คู่กับหมวดหมู่ใหม่ทันที!
                ai_classifier.learn(
                    text=updated_txn.description,
                    category_obj=updated_txn.category,
                    user=request.user
                )
            # -----------------------------

            messages.success(request, "แก้ไขรายการเรียบร้อย (AI เรียนรู้แล้ว!)")
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