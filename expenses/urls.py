from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from expenses import views 

urlpatterns = [
    path('', views.dashboard, name='dashboard'), # ตั้งเป็นหน้าแรก (Home)
    path('profile/', views.profile, name='profile'),
    path('profile/change-password/', views.change_password_modal, name='change_password_modal'),
    path('profile/set-password-modal/', views.set_password_modal, name='set_password_modal'),
    path('profile/delete/', views.delete_account, name='delete_account'),
    # path('onboarding/', views.profile_edit_view, name="profile-onboarding"),

    path('add/', views.add_smart_transaction, name='add_smart_transaction'),
    path('import/', views.import_data, name='import_data'),
    path('import/template/', views.download_template, name='download_template'),


    # admin management
    path('management/keyword_manager/', views.keyword_manager, name='keyword_manager'),
    path('management/keyword_manager/add/', views.add_keyword, name='add_keyword'),

    path('management/users/', views.admin_user_list, name='admin_user_list'),
    path('management/users/toggle/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('management/users/<int:user_id>/edit/', views.admin_user_edit, name='admin_user_edit'),
    path('management/users/<int:user_id>/delete/', views.admin_user_delete, name='admin_user_delete'),

    # ไม่ไดเใช้แล้ว
    # path('ai-manager/', views.ai_manager, name='ai_manager'),
    # path('ai-manager/template/', views.download_ai_template, name='download_ai_template'),

    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transaction/edit/<int:transaction_id>/', views.edit_transaction, name='edit_transaction'),
    path('transaction/delete/<int:transaction_id>/', views.delete_transaction, name='delete_transaction'),
    path('transactions/delete-multiple/', views.delete_multiple_transactions, name='delete_multiple_transactions'),

    path('categories/', views.manage_categories, name='manage_categories'),
    # path('categories/edit/<int:cat_id>/', views.edit_category, name='edit_category'),
    path('categories/delete/<int:cat_id>/', views.delete_category, name='delete_category'),

    path('budget/', views.manage_budget, name='manage_budget'),
    path('budget/edit/<int:budget_id>/', views.edit_budget, name='edit_budget'),
    path('budget/delete/<int:budget_id>/', views.delete_budget, name='delete_budget'),

    # path('admin/users/', views.admin_user_list, name='admin_user_list'),
    # about login
    # path('confirm-link/', views.confirm_account_link, name='confirm_account_link'),
    
    # password reset
    path('reset_password/', auth_views.PasswordResetView.as_view(template_name="account/password_reset.html",
        email_template_name="account/password_reset_email.html", subject_template_name="account/password_reset_subject.txt"
        ), name="reset_password"),
        
    path('reset_password_sent/', auth_views.PasswordResetDoneView.as_view(template_name="account/password_reset_done.html"), name="password_reset_done"),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name="account/password_reset_confirm.html"), name="password_reset_confirm"),
    path('reset_password_complete/', auth_views.PasswordResetCompleteView.as_view(template_name="account/password_reset_complete.html"), name="password_reset_complete"),

]