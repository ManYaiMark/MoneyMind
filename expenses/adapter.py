import requests
from django.core.files.base import ContentFile
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.exceptions import ImmediateHttpResponse

from django.shortcuts import redirect , resolve_url
from django.urls import reverse
from django.contrib.auth import get_user_model
from expenses.models import SocialLinkConfirmation
from django import forms

User = get_user_model()

class CustomAccountAdapter(DefaultAccountAdapter):
    def get_signup_redirect_url(self, request):
        return resolve_url("profile-onboarding") 

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        email = sociallogin.account.extra_data.get("email")
        
        if not email:
            return
        
        if not sociallogin.is_existing:
            existing_user = User.objects.filter(email=email).first()
            if existing_user:
                sociallogin.connect(request, existing_user)
        
        if sociallogin.is_existing: 
            user = sociallogin.user
            email_address, created = EmailAddress.objects.get_or_create(user=user, email=email)
            if not email_address.verified:
                email_address.verified = True
                email_address.save()
                
                
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        email = user.email
        email_address, created = EmailAddress.objects.get_or_create(user=user, email=email)
        if not email_address.verified:
            email_address.verified = True
            email_address.save()
            
        return user

class MyAccountAdapter(DefaultAccountAdapter):
    def clean_email(self, email):
        email = super().clean_email(email)
        user = User.objects.filter(email__iexact=email).first()
        
        if user and not user.has_usable_password():
            raise forms.ValidationError("อีเมลนี้เชื่อมต่อกับ Google ไว้แล้ว กรุณาเข้าสู่ระบบด้วย Google")
        
        return email