from django.urls import path
from . import views

urlpatterns = [
    path('receipt_tbl/', views.receipt_tbl, name='receipt_tbl'),
    path('payment_tbl/', views.payment_tbl, name='payment_tbl'),
    path('finance_list_tbl/', views.finance_list_tbl, name='finance_list_tbl'),
    path('cashbook_tbl/', views.cashbook_tbl, name='cashbook_tbl'),
    path('api/receipts/', views.api_get_receipts, name='api_get_receipts'),
    path('api/receipts/summary/', views.api_receipt_summary, name='api_receipt_summary'),
    path('api/receipts/save/', views.api_save_receipt, name='api_save_receipt'),
    path('api/receipts/delete/', views.api_delete_receipt, name='api_delete_receipt'),
    path('api/orders_for_receipt/', views.api_get_orders_for_receipt, name='api_get_orders_for_receipt'),
    path('api/payments/', views.api_get_payments, name='api_get_payments'),
    path('api/payments/save/', views.api_save_payment, name='api_save_payment'),
    path('api/payments/delete/', views.api_delete_payment, name='api_delete_payment'),
    path('api/finance_categories/', views.api_get_finance_categories, name='api_get_finance_categories'),
    path('api/finance_categories/save/', views.api_save_finance_category, name='api_save_finance_category'),
    path('api/cashbooks/', views.api_get_cashbooks, name='api_get_cashbooks'),
    path('api/cashbooks/save/', views.api_save_cashbook, name='api_save_cashbook'),
    path('api/payment_methods/', views.api_get_payment_methods, name='api_get_payment_methods'),
    path('api/payment_methods/save/', views.api_save_payment_method, name='api_save_payment_method'),
    path('api/payment_methods/delete/', views.api_delete_payment_method, name='api_delete_payment_method'),
    path('setting_payment_methods/', views.setting_payment_methods, name='setting_payment_methods'),
    path('api/receipts/export_excel/', views.export_receipts_excel, name='export_receipts_excel'),
    path('api/payments/export_excel/', views.export_payments_excel, name='export_payments_excel'),
]
