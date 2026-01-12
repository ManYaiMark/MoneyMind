import pandas as pd
import joblib
import os
from sklearn.feature_extraction.text import CountVectorizer
# เปลี่ยนจาก Naive Bayes เป็น LinearSVC (ฉลาดกว่าในเคสนี้)
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import make_pipeline
from pythainlp.tokenize import word_tokenize
from django.conf import settings
from .models import TrainingData, Category

MODEL_PATH = os.path.join(settings.BASE_DIR, 'ml_models', 'category_classifier.pkl')

if not os.path.exists(os.path.dirname(MODEL_PATH)):
    os.makedirs(os.path.dirname(MODEL_PATH))

class CategoryClassifier:
    def __init__(self):
        self.model = None
        self.load_model()

    def load_model(self):
        if os.path.exists(MODEL_PATH):
            try:
                self.model = joblib.load(MODEL_PATH)
            except:
                self.train_model()
        else:
            self.train_model()

    def thai_tokenizer(self, text):
        return word_tokenize(text, engine="newmm")

    def train_model(self):
        data = TrainingData.objects.all().values('text', 'category__name')
        df = pd.DataFrame(list(data))

        if df.empty:
            self.model = None
            return

        X = df['text']
        y = df['category__name']

        # 🔥 เปลี่ยนโมเดล: ใช้ LinearSVC (ฉลาดและแม่นยำกว่าสำหรับ Text สั้นๆ)
        # ใช้ CalibratedClassifierCV ครอบเพื่อให้มันบอก % ความมั่นใจได้ (ปกติ SVM บอกไม่ได้)
        svm = LinearSVC(class_weight='balanced', random_state=42) # class_weight='balanced' ช่วยแก้เรื่องข้อมูลน้อย
        clf = CalibratedClassifierCV(svm) 

        self.model = make_pipeline(
            CountVectorizer(tokenizer=self.thai_tokenizer),
            clf
        )
        self.model.fit(X, y)
        
        joblib.dump(self.model, MODEL_PATH)
        print("✅ Model Re-trained Successfully (Linear SVM)!")

    def predict(self, text):
        # 🌟 LOGIC ใหม่: เช็ค "โพย" (Training Data) ก่อนเสมอ!
        # ถ้า User เคยสอนคำนี้เป๊ะๆ ให้ตอบเลย ไม่ต้องให้ AI เดา
        exact_match = TrainingData.objects.filter(text__iexact=text).first()
        if exact_match:
            print(f"🎯 [AI] Exact Match Found in Training Data: {text} -> {exact_match.category.name}")
            return exact_match.category, 1.0 # มั่นใจ 100%

        # ถ้าไม่มีในโพย ค่อยให้ AI เดา
        if not self.model:
            return None, 0.0

        try:
            cat_name = self.model.predict([text])[0]
            prob = self.model.predict_proba([text]).max()
            
            print(f"🤖 [AI] SVM Guess: '{text}' -> '{cat_name}' ({prob:.2f})")

            category_obj = Category.objects.filter(name__iexact=cat_name).first()
            return category_obj, prob
            
        except Exception as e:
            print(f"❌ [AI] Error: {e}")
            return None, 0.0

    def learn(self, text, category_obj, user=None):
        TrainingData.objects.create(
            text=text,
            category=category_obj,
            user=user,
            is_verified=True
        )
        self.train_model()

ai_classifier = CategoryClassifier()