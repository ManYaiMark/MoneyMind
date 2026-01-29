# expenses/utils.py
from thefuzz import process
from .models import CategoryKeyword

def predict_category_fuzzy(user_text):
    # 1. ดึงคำศัพท์ทั้งหมดจาก Database ออกมา
    # values_list จะดึงมาเฉพาะ field 'word' ให้เป็น list ไวๆ
    # เช่น ['7-Eleven', 'เซเว่น', 'ข้าวมันไก่', ...]
    keywords_query = CategoryKeyword.objects.all().values_list('word', flat=True)
    all_keywords = list(keywords_query)

    if not all_keywords:
        return None, None, 0

    # 2. ใช้ Fuzzy หาคำที่เหมือนที่สุด
    # user_text: สิ่งที่ user พิมพ์มา (เช่น "เงินเดือ")
    best_match = process.extractOne(user_text, all_keywords)
    
    # best_match จะได้ ('เงินเดือน', 88)
    if best_match:
        matched_word = best_match[0]
        score = best_match[1]

        # 3. ถ้าคะแนนเกิน 60% ให้ไปดึง Category ตัวจริงมาตอบ
        if score >= 60:
            keyword_obj = CategoryKeyword.objects.get(word=matched_word)
            return keyword_obj.category, matched_word, score

    return None, None, 0