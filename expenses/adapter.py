from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        # 🔥 นี่คือจุดที่เราสั่ง Print Error ออกมาดู
        print("\n" + "="*40)
        print(f"❌ GOOGLE LOGIN FAILED! (Provider: {provider_id})")
        print(f"▶ Error Type: {error}")
        print(f"▶ Exception Detail: {exception}")
        
        if extra_context:
            print(f"▶ Extra Context: {extra_context}")
            
        print("="*40 + "\n")
        
        # ส่งงานต่อให้ระบบเดิมทำงาน (จะได้ไม่พัง)
        super().authentication_error(request, provider_id, error, exception, extra_context)