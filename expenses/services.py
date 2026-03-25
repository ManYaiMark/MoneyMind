# import pandas as pd
# import joblib
# import os
# from sklearn.feature_extraction.text import CountVectorizer
# เปลี่ยนจาก Naive Bayes เป็น LinearSVC (ฉลาดกว่าในเคสนี้)
# from sklearn.svm import LinearSVC
# from sklearn.calibration import CalibratedClassifierCV
# from sklearn.pipeline import make_pipeline
# from pythainlp.tokenize import word_tokenize
# from django.conf import settings
from .models import Transaction, Budget

from datetime import datetime, timedelta, date
import calendar
import json
from django.utils import timezone
from django.db.models.functions import TruncDay, TruncMonth
from django.db.models import Sum, Case, When, FloatField

# MODEL_PATH = os.path.join(settings.BASE_DIR, 'ml_models', 'category_classifier.pkl')

# if not os.path.exists(os.path.dirname(MODEL_PATH)):
#     os.makedirs(os.path.dirname(MODEL_PATH))


def get_dashboard_context(user, date_str):
    # ฟังก์ชันสำหรับคำนวณและเตรียมข้อมูลทั้งหมดของหน้า Dashboard 

    today = timezone.now().date()
    try:
        ref_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else today
    except ValueError:
        ref_date = today

    curr_month, curr_year = ref_date.month, ref_date.year
    days_in_month = calendar.monthrange(curr_year, curr_month)[1]
    month_start = date(curr_year, curr_month, 1)
    month_end = date(curr_year, curr_month, days_in_month)

    # คำนวณยอดเงินรวมและยอดประจำเดือน
    total_balance = float(Transaction.objects.filter(user=user).aggregate(balance=Sum('amount'))['balance'] or 0)
    monthly_stats = Transaction.objects.filter(user=user, date__range=[month_start, month_end]).aggregate(
        income=Sum(Case(When(amount__gt=0, then='amount'), output_field=FloatField())),
        expense=Sum(Case(When(amount__lt=0, then='amount'), output_field=FloatField()))
    )
    m_income = float(monthly_stats['income'] or 0)
    m_expense = float(abs(monthly_stats['expense'] or 0))
    
    budget_query = Budget.objects.filter(user=user, month=curr_month, year=curr_year)
    total_budget = float(budget_query.aggregate(Sum('amount_limit'))['amount_limit__sum'] or 0)
    remaining_budget = total_budget - m_expense

    COLOR_MAP = {
        'primary': '#0d6efd', 'success': '#198754', 'danger': '#dc3545',
        'warning': '#ffc107', 'info': '#0dcaf0', 'secondary': '#6c757d',
        'dark': '#212529', 'light': '#f8f9fa',
    }

    pie_data = Transaction.objects.filter(user=user, date__range=[month_start, month_end], amount__lt=0).values('category__name', 'category__color').annotate(total=Sum('amount'))
    pie_labels = [item['category__name'] or "ไม่ระบุ" for item in pie_data]
    pie_values = [float(abs(item['total'])) for item in pie_data]
    pie_colors = [COLOR_MAP.get(item['category__color'], '#858796') for item in pie_data]

    six_months_ago = month_start - timedelta(days=180)
    bar_data = Transaction.objects.filter(user=user, date__range=[six_months_ago, month_end]).annotate(month_label=TruncMonth('date')).values('month_label').annotate(
        inc=Sum(Case(When(amount__gt=0, then='amount'), output_field=FloatField())),
        exp=Sum(Case(When(amount__lt=0, then='amount'), output_field=FloatField()))
    ).order_by('month_label')
    bar_labels = [item['month_label'].strftime('%b %Y') for item in bar_data]
    bar_income = [float(item['inc'] or 0) for item in bar_data]
    bar_expense = [float(abs(item['exp'] or 0)) for item in bar_data]

    opening_balance = float(Transaction.objects.filter(user=user, date__lt=month_start).aggregate(Sum('amount'))['amount__sum'] or 0)
    daily_txns = Transaction.objects.filter(user=user, date__range=[month_start, month_end]).annotate(day=TruncDay('date')).values('day').annotate(daily_sum=Sum('amount')).order_by('day')
    line_labels = [str(i) for i in range(1, days_in_month + 1)]
    line_values = []
    daily_map = {item['day'].day: float(item['daily_sum'] or 0) for item in daily_txns}
    current_running_balance = opening_balance
    
    for d in range(1, days_in_month + 1):
        current_running_balance += daily_map.get(d, 0.0)
        if ref_date.year < today.year or (ref_date.year == today.year and ref_date.month < today.month) or d <= today.day:
            line_values.append(current_running_balance)

    recent_transactions = Transaction.objects.filter(user=user, date__range=[month_start, month_end]).order_by('-date', '-created_at')[:5]
    top_cat = pie_data.order_by('total').first()
    
    # ตรวจสอบการแจ้งเตือนงบประมาณที่ใกล้เกินกำหนด
    budget_status_list = []
    budget_alerts = []
    for b in budget_query:
        spent = abs(float(Transaction.objects.filter(user=user, category=b.category, date__range=[month_start, month_end]).aggregate(Sum('amount'))['amount__sum'] or 0))
        limit = float(b.amount_limit)
        percent = (spent / limit * 100) if limit > 0 else 0
        budget_status_list.append({'name': b.category.name, 'remaining': limit - spent, 'percent': round(percent, 1), 'limit': limit})
        if percent >= 80: budget_alerts.append({'name': b.category.name, 'percent': round(percent, 1)})

    critical_budget = sorted(budget_status_list, key=lambda x: x['remaining'])[0] if budget_status_list else None
    thai_months = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    
    # ส่งคืนข้อมูลทั้งหมดกลับไปยังส่วนควบคุมการแสดงผล
    return {
        'total_balance': total_balance, 'm_income': m_income, 'm_expense': m_expense,
        'remaining_budget': remaining_budget, 'critical_budget': critical_budget, 'net_cash_flow': m_income - m_expense,
        'pie_labels': json.dumps(pie_labels), 'pie_values': json.dumps(pie_values), 'pie_colors': json.dumps(pie_colors),
        'bar_labels': json.dumps(bar_labels), 'bar_income': json.dumps(bar_income), 'bar_expense': json.dumps(bar_expense),
        'line_labels': json.dumps(line_labels), 'line_values': json.dumps(line_values),
        'recent_transactions': recent_transactions, 'top_spending_cat': top_cat['category__name'] if top_cat else "ไม่มีข้อมูล",
        'budget_alerts': budget_alerts, 'current_month_name': thai_months[curr_month],
        'current_year': curr_year + 543, 'prev_month_url': f"?date={month_start - timedelta(days=1)}",
        'next_month_url': f"?date={month_end + timedelta(days=1)}",
    }

