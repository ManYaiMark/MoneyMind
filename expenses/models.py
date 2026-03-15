import os

from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings

from django.db import models
from django.db.models.signals import post_save ,pre_save, post_delete
from django.dispatch import receiver

from allauth.socialaccount.models import SocialAccount

# class SocialLinkConfirmation(models.Model):
#     user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_confirmation')
#     confirmed_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.user.email} confirmed at {self.confirmed_at}"

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    avatar_color = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return f'{self.user.username} Profile'
    
    @property
    def is_google_login(self):
        return SocialAccount.objects.filter(user=self.user, provider='google').exists()
    

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    # เช็คก่อนว่ามี profile ไหม ถ้าไม่มีให้สร้าง (กันเหนียวสำหรับ user เก่า)
    if not hasattr(instance, 'profile'):
        Profile.objects.create(user=instance)
    instance.profile.save()


# ลบ file if ลบ user
@receiver(post_delete, sender=Profile)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    if instance.profile_picture:
        if os.path.isfile(instance.profile_picture.path):
            os.remove(instance.profile_picture.path)

# ลบ file if เปลี่ยนรูปโปรไฟล์
@receiver(pre_save, sender=Profile)
def auto_delete_file_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return False

    try:
        # ดึงข้อมูล Profile เก่าจาก Database
        old_profile = Profile.objects.get(pk=instance.pk)
        old_file = old_profile.profile_picture
    except Profile.DoesNotExist:
        return False

    new_file = instance.profile_picture
    
    # ถ้ามีการเปลี่ยนรูป (รูปเก่า ไม่เท่ากับ รูปใหม่)
    if not old_file == new_file:
        try:
            # เช็คว่ามีรูปเก่าจริงๆ ใช่ไหม (กัน Error)
            if old_file and old_file.name:
                if os.path.isfile(old_file.path):
                    os.remove(old_file.path)
        except Exception:
            # 🔥 จุดสำคัญ: ถ้าลบไม่ได้ หรือหาไฟล์ไม่เจอ ให้ปล่อยผ่านไปเลย
            # อย่าให้ระบบล่ม (Login Google จะได้ไม่พัง)
            pass


class Category(models.Model):
    TYPE_CHOICES = [
        ('INCOME', 'รายรับ'),
        ('EXPENSE', 'รายจ่าย')
    ]

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='EXPENSE')
    is_global = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    icon = models.CharField(max_length=50, default='bi-tags-fill', verbose_name='ไอคอน')
    color = models.CharField(max_length=20, default='secondary', verbose_name='สี')

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"
    

# class UserCategoryPreference(models.Model):
#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     category = models.ForeignKey(Category, on_delete=models.CASCADE)
#     is_hidden = models.BooleanField(default=False)

#     class Meta:
#         unique_together = ('user', 'category')
        

class Budget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    amount_limit = models.DecimalField(max_digits=10, decimal_places=2)
    month = models.IntegerField()
    year = models.IntegerField()

    class Meta:
        unique_together = ('user', 'category', 'month', 'year')

    def __str__(self):
        return f"Budget: {self.category.name} - {self.amount_limit}"

class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255)
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} - {self.amount}"
    
# class TrainingData(models.Model):
#     user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True) 
#     text = models.CharField(max_length=255)       
#     category = models.ForeignKey(Category, on_delete=models.CASCADE)  
#     is_verified = models.BooleanField(default=False) 
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.text} -> {self.category.name}"
    
class CategoryKeyword(models.Model):
    word = models.CharField(max_length=100, unique=True, verbose_name="คำค้นหา (Keyword)")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, verbose_name="หมวดหมู่ที่คู่กัน")
    
    def __str__(self):
        return f"{self.word} -> {self.category.name}"