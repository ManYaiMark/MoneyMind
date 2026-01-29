from django.contrib import admin
from .models import Profile, Category, Budget, Transaction, CategoryKeyword

# Register your models here.
admin.site.register(Profile)
admin.site.register(Category)   
admin.site.register(Budget)
admin.site.register(Transaction)

@admin.register(CategoryKeyword)
class CategoryKeywordAdmin(admin.ModelAdmin):
    list_display = ('word', 'category')
    search_fields = ('word', 'category__name')