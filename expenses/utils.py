# expenses/utils.py
import os
import tempfile
import re
import pandas as pd
from datetime import datetime
from thefuzz import process
from .models import CategoryKeyword, Category, Transaction

def predict_category_fuzzy(user_text):
    keywords_query = CategoryKeyword.objects.all().values_list('word', flat=True)
    all_keywords = list(keywords_query)

    if not all_keywords:
        return None, None, 0

    best_match = process.extractOne(user_text, all_keywords)
    
    if best_match:
        matched_word = best_match[0]
        score = best_match[1]

        if score >= 60:
            keyword_obj = CategoryKeyword.objects.get(word=matched_word)
            return keyword_obj.category, matched_word, score

    return None, None, 0


def parse_smart_transactions(raw_data, user):
    lines = raw_data.strip().split('\n')
    preview_list = []
    current_date = datetime.now().date()
    fallback_cat = Category.objects.filter(name="อื่นๆ", is_global=True).first()

    for line in lines:
        line = line.strip()
        if not line: continue

        date_obj = current_date
        # เปลี่ยนจาก \b เป็น (?<!\d) และ (?!\d) เพื่อให้จับวันที่ได้แม้พิมพ์ติดกับตัวหนังสือ (เช่น 12/05ข้าว)
        date_match = re.search(r'(?<!\d)(\d{1,2})[-/](\d{1,2})(?:[-/](\d{2,4}))?(?!\d)', line)
        
        if date_match:
            d, m, y_str = date_match.groups()
            try:
                year = int(y_str) if y_str else current_date.year
                if year < 100: year += 2000 
                if year > 2400: year -= 543
                date_obj = datetime(year, int(m), int(d)).date()
                current_date = date_obj # ✅ จำวันที่ไว้ใช้กับบรรทัดถัดๆ ไปที่ไม่ได้ระบุวันที่
                line = line.replace(date_match.group(0), '').strip()
            except ValueError:
                pass

        description = "รายการทั่วไป"
        final_amount = 0.0
        num_re = r'([+-]?[0-9,]+(?:\.\d+)?)'

        match_front = re.match(r'^' + num_re + r'\s+(.*)$', line)
        match_back = re.match(r'^(.*)\s+' + num_re + r'$', line)

        amount_str = "0"
        if match_front:
            amount_str = match_front.group(1)
            description = match_front.group(2).strip()
        elif match_back:
            description = match_back.group(1).strip()
            amount_str = match_back.group(2)
        else:
            try:
                test_amt = float(line.replace(',', ''))
                amount_str = line
            except ValueError:
                continue

        try:
            amount_val = float(amount_str.replace(',', ''))
            final_amount = -abs(amount_val) if '-' in amount_str else abs(amount_val)
        except ValueError:
            continue

        cat_id, category_name, cat_icon, cat_color, is_uncertain = "", "-", "bi-question-circle", "secondary", False
        prev = Transaction.objects.filter(user=user, description__iexact=description).order_by('-created_at').first()
        
        if prev and prev.category:
            cat_id, category_name, cat_icon, cat_color = prev.category.id, prev.category.name, prev.category.icon, prev.category.color
        else:
            predicted_cat, matched_word, score = predict_category_fuzzy(description)
            if predicted_cat:
                cat_id, category_name, cat_icon, cat_color = predicted_cat.id, predicted_cat.name, predicted_cat.icon, predicted_cat.color
                if score < 70: is_uncertain = True
            elif fallback_cat:
                cat_id, category_name, cat_icon, cat_color, is_uncertain = fallback_cat.id, fallback_cat.name, fallback_cat.icon, fallback_cat.color, True
            else: is_uncertain = True

        preview_list.append({
            'date': date_obj.strftime('%Y-%m-%d'), 'description': description, 'amount': final_amount,
            'cat_id': cat_id, 'category_name': category_name, 'icon': cat_icon, 'color': cat_color, 'is_uncertain': is_uncertain
        })
        
    return preview_list


def process_uploaded_file(file, user):
    """ อ่านและประมวลผลไฟล์ (CSV, Excel, TXT) สำหรับนำเข้าข้อมูล """
    tmp_file_path = None
    preview_list = []
    messages_list = []

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
        fallback_cat = Category.objects.filter(name="อื่นๆ", is_global=True).first()

        if file.name.endswith('.txt'):
            current_date = datetime.now().date()
            with open(tmp_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    
                    date_obj = current_date
                    date_match = re.search(r'(?<!\d)(\d{1,2})[-/](\d{1,2})(?:[-/](\d{2,4}))?(?!\d)', line)
                    
                    if date_match:
                        d, m, y_str = date_match.groups()
                        try:
                            year = int(y_str) if y_str else current_date.year
                            if year < 100: year += 2000 
                            if year > 2400: year -= 543
                            date_obj = datetime(year, int(m), int(d)).date()
                            current_date = date_obj # ✅ จำวันที่ไว้ใช้กับบรรทัดถัดๆ ไป
                            line = line.replace(date_match.group(0), '').strip()
                        except ValueError:
                            pass
                    
                    amount_match = re.search(r'([+-]?[0-9,]+(\.\d+)?)', line)
                    if amount_match:
                        amt_str = amount_match.group(1)
                        try:
                            amount_val = float(amt_str.replace(',', ''))
                        except ValueError: continue
                        
                        if '-' in amt_str: final_amount = -abs(amount_val)
                        else: final_amount = abs(amount_val)

                        description = line.replace(amt_str, '').strip() or "รายการทั่วไป"
                        data_list.append({'date': date_obj, 'amount': final_amount, 'description': description, 'category': None})
            
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
                        if isinstance(raw_date, str): txn_date = pd.to_datetime(raw_date, dayfirst=True).date()
                        elif isinstance(raw_date, (datetime, pd.Timestamp)): txn_date = raw_date.date()
                        else: txn_date = datetime.now().date()
                    else:
                        txn_date = datetime.now().date()

                    description = str(row['description']).strip()
                    cat_id, cat_name, cat_icon, cat_color, is_uncertain = "", "-", "bi-question-circle", "secondary", False

                    if 'category' in df.columns and pd.notna(row['category']):
                        c = Category.objects.filter(name__iexact=str(row['category']).strip()).first()
                        if c: cat_id, cat_name, cat_icon, cat_color = c.id, c.name, c.icon, c.color

                    if not cat_id:
                        prev = Transaction.objects.filter(user=user, description__iexact=description).order_by('-created_at').first()
                        if prev and prev.category:
                            cat_id, cat_name, cat_icon, cat_color = prev.category.id, prev.category.name, prev.category.icon, prev.category.color

                    if not cat_id:
                        predicted_cat, matched_word, score = predict_category_fuzzy(description)
                        if predicted_cat:
                            cat_id, cat_name, cat_icon, cat_color = predicted_cat.id, predicted_cat.name, predicted_cat.icon, predicted_cat.color
                            if score < 75: is_uncertain = True
                        elif fallback_cat:
                            cat_id, cat_name, cat_icon, cat_color, is_uncertain = fallback_cat.id, fallback_cat.name, fallback_cat.icon, fallback_cat.color, True

                    preview_list.append({
                        'date': txn_date.strftime('%Y-%m-%d'), 'description': description, 'amount': amt,
                        'cat_id': cat_id, 'category_name': cat_name, 'icon': cat_icon, 'color': cat_color, 'is_uncertain': is_uncertain
                    })
                except: continue
        else:
            missing = []
            if 'amount' not in df.columns: missing.append('จำนวนเงิน (Amount)')
            if 'description' not in df.columns: missing.append('รายการ (Description)')
            messages_list.append(('error', f"ไฟล์ไม่ถูกต้อง ขาดคอลัมน์: {', '.join(missing)}"))

        if not preview_list and not messages_list:
            messages_list.append(('warning', "ไม่พบข้อมูลรายการในไฟล์"))

    except Exception as e:
        messages_list.append(('error', f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}"))
    finally:
        if tmp_file_path and os.path.exists(tmp_file_path): os.remove(tmp_file_path)

    return preview_list, messages_list