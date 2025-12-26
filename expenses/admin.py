from django.contrib import admin
from .models import Profile, Category, Budget, Transaction

# Register your models here.
admin.site.register(Profile)
admin.site.register(Category)   
admin.site.register(Budget)
admin.site.register(Transaction)