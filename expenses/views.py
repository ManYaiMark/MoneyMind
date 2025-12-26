import re
import json 
from datetime import datetime, timedelta
import pandas as pd
import io
import os
import tempfile


from django.db.models import Sum , Q
from django.shortcuts import render, redirect, get_object_or_404  
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .models import Transaction, Category, Budget
from .forms import SmartInputForm, CategoryForm, BudgetForm , UploadFileForm , TransactionForm


@login_required
def add_smart_transaction(request):
    if request.method == 'POST':
        form = SmartInputForm(request.POST)
        if form.is_valid():
            raw_data = form.cleaned_data['raw_data']
            current_date = datetime.now().date()
            lines = raw_data.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line: continue

                date_match = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})', line)
                if date_match and len(line) <= 10: 
                    day, month, year = map(int, date_match.groups())
                    if year < 100: year += 2000 
                    try:
                        current_date = datetime(year, month, day).date()
                    except ValueError: pass
                    continue 

                amount_match = re.search(r'([+-]?\d+(\.\d+)?)', line)
                if amount_match:
                    amount_str = amount_match.group(1)
                    amount_val = float(amount_str)
                    
                    if '-' in amount_str: final_amount = amount_val 
                    elif '+' in amount_str: final_amount = amount_val
                    else: final_amount = -abs(amount_val)

                    description = line.replace(amount_str, '').strip()
                    if date_match: description = description.replace(date_match.group(0), '').strip()
                    if not description: description = "รายการทั่วไป"

                    category = None
                    
                    prev_txn = Transaction.objects.filter(user=request.user, description__iexact=description).order_by('-created_at').first()
                    if prev_txn: category = prev_txn.category
                    
                    Transaction.objects.create(
                        user=request.user if request.user.is_authenticated else None, 
                        amount=final_amount,
                        description=description,
                        date=current_date,
                        category=category
                    )
            
            messages.success(request, "บันทึกข้อมูลเรียบร้อยแล้ว!")
            return redirect('add_smart_transaction')
    else:
        form = SmartInputForm()

    return render(request, 'expenses/add_smart.html', {'form': form})


@login_required
def download_template(request):
    file_format = request.GET.get('format', 'xlsx')
    
    # ข้อมูลตัวอย่างสำหรับ Excel/CSV
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
        # สร้างเนื้อหาไฟล์ Text ตามรูปแบบที่คุณต้องการ
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
        
    else: # Default เป็น Excel
        df = pd.DataFrame(data)
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="moneymind_template.xlsx"'
        df.to_excel(response, index=False)
        return response

@login_required
def import_data(request):
    if request.method == 'POST':
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

                if file.name.endswith('.csv'):
                    df = pd.read_csv(tmp_file_path, encoding='utf-8-sig')
                elif file.name.endswith('.xls'):
                    df = pd.read_excel(tmp_file_path, engine='xlrd')
                elif file.name.endswith('.xlsx'):
                    df = pd.read_excel(tmp_file_path, engine='openpyxl')
                elif file.name.endswith('.txt'):
                    
                    data_list = []
                    current_date = datetime.now().date()
                    
                    with open(tmp_file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line: continue
                            
                            # 1. เช็คว่าเป็นบรรทัด "วันที่" หรือไม่ (เช่น 25/12/2025)
                            date_match = re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$', line)
                            if date_match:
                                d, m, y = map(int, date_match.groups())
                                if y < 100: y += 2000
                                try:
                                    current_date = datetime(y, m, d).date()
                                except ValueError: pass
                                continue 

                            # 2. ถ้าไม่ใช่บรรทัดวันที่ ให้มองเป็น "รายการ"
                            amount_match = re.search(r'([+-]?\d+(\.\d+)?)', line)
                            if amount_match:
                                amt_str = amount_match.group(1)
                                try:
                                    amount_val = float(amt_str)
                                    final_amount = amount_val 
                                except ValueError: continue

                                description = line.replace(amt_str, '').strip()
                                if not description: description = "รายการทั่วไป"
                                
                                data_list.append({
                                    'date': current_date,
                                    'amount': final_amount,
                                    'description': description,
                                    'category': None 
                                })
                    
                    df = pd.DataFrame(data_list)

                # จัดการ Header สำหรับไฟล์ Excel/CSV (Text file ผ่านขั้นตอนนี้ไปแล้ว)
                if not file.name.endswith('.txt'):
                    df.columns = df.columns.str.strip()
                    column_mapping = {
                        'วันที่': 'date', 'Date': 'date', 'date': 'date',
                        'รายการ': 'description', 'Description': 'description', 'description': 'description', 'ชื่อรายการ': 'description',
                        'จำนวนเงิน': 'amount', 'Amount': 'amount', 'amount': 'amount', 'ราคา': 'amount', 'จำนวน': 'amount',
                        'หมวดหมู่': 'category', 'Category': 'category', 'category': 'category'
                    }
                    df.rename(columns=column_mapping, inplace=True)

                if 'amount' in df.columns and 'description' in df.columns:
                    df.dropna(subset=['amount', 'description'], inplace=True)
                
                # ตรวจสอบว่ามี Column ครบไหม
                required_cols = ['date', 'amount', 'description']
                missing_cols = [col for col in required_cols if col not in df.columns]
                
                if missing_cols:
                    messages.error(request, f"ไฟล์ไม่ถูกต้อง! ขาดคอลัมน์: {', '.join(missing_cols)}")
                    os.remove(tmp_file_path)
                    return redirect('import_data')

                # เตรียมบันทึกลง Database
                transactions_to_create = []
                
                for _, row in df.iterrows():
                    try:
                        amt = float(row['amount'])
                        if pd.isna(amt): continue
                    except: continue

                    try:
                        if isinstance(row['date'], str):
                            txn_date = pd.to_datetime(row['date'], dayfirst=True).date()
                        else:
                            txn_date = row['date']
                    except:
                        txn_date = datetime.now().date()

                    cat_obj = None
                    # พยายามหาหมวดหมู่
                    if 'category' in df.columns and pd.notna(row['category']):
                        cat_name = str(row['category']).strip()
                        cat_obj = Category.objects.filter(name__iexact=cat_name).first()
                    elif file.name.endswith('.txt'):
                        # เดาหมวดหมู่จากประวัติเก่า
                        prev = Transaction.objects.filter(user=request.user, description__iexact=str(row['description'])).first()
                        if prev: cat_obj = prev.category

                    transactions_to_create.append(
                        Transaction(
                            user=request.user,
                            description=str(row['description']).strip(),
                            amount=amt,
                            date=txn_date,
                            category=cat_obj
                        )
                    )

                if transactions_to_create:
                    Transaction.objects.bulk_create(transactions_to_create)
                    messages.success(request, f"นำเข้าข้อมูลสำเร็จ {len(transactions_to_create)} รายการ!")
                else:
                    messages.warning(request, "ไม่พบข้อมูลที่นำเข้าได้")
                
            except Exception as e:
                messages.error(request, f"เกิดข้อผิดพลาด: {str(e)}")
            
            finally:
                if tmp_file_path and os.path.exists(tmp_file_path):
                    os.remove(tmp_file_path)
                
            return redirect('dashboard')
    else:
        form = UploadFileForm()

    return render(request, 'expenses/import_data.html', {'form': form})



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
            form.save()
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


def edit_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "แก้ไขหมวดหมู่เรียบร้อย!")
            return redirect('manage_categories')
    return redirect('manage_categories')


def delete_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category.delete()
    messages.success(request, "ลบหมวดหมู่เรียบร้อย!")
    return redirect('manage_categories')

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

def delete_budget(request, budget_id):
    budget = get_object_or_404(Budget, id=budget_id)
    budget.delete()
    messages.success(request, "ลบงบประมาณเรียบร้อย!")
    return redirect('manage_budget')