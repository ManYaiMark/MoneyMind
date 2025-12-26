from django.contrib import admin
from django.urls import path
from expenses import views 

urlpatterns = [
    path('', views.dashboard, name='dashboard'), # ตั้งเป็นหน้าแรก (Home)
    path('add/', views.add_smart_transaction, name='add_smart_transaction'),
    path('import/', views.import_data, name='import_data'),
    path('import/template/', views.download_template, name='download_template'),

    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transaction/edit/<int:transaction_id>/', views.edit_transaction, name='edit_transaction'),
    path('transaction/delete/<int:transaction_id>/', views.delete_transaction, name='delete_transaction'),

    path('categories/', views.manage_categories, name='manage_categories'),
    path('categories/edit/<int:category_id>/', views.edit_category, name='edit_category'),
    path('categories/delete/<int:category_id>/', views.delete_category, name='delete_category'),

    path('budget/', views.manage_budget, name='manage_budget'),
    path('budget/edit/<int:budget_id>/', views.edit_budget, name='edit_budget'),
    path('budget/delete/<int:budget_id>/', views.delete_budget, name='delete_budget'),

]