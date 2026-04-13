from django.urls import path
from . import views

urlpatterns = [
    path('report_sales/', views.report_sales, name='report_sales'),
    path('api/report_sales/', views.api_report_sales, name='api_report_sales'),
    path('report_purchases/', views.report_purchases, name='report_purchases'),
    path('api/report_purchases/', views.api_report_purchases, name='api_report_purchases'),
    path('report_inventory/', views.report_inventory, name='report_inventory'),
    path('api/report_inventory/', views.api_report_inventory, name='api_report_inventory'),
    path('report_finance/', views.report_finance, name='report_finance'),
    path('api/report_finance/', views.api_report_finance, name='api_report_finance'),
    path('report_customers/', views.report_customers, name='report_customers'),
    path('api/report_customers/', views.api_report_customers, name='api_report_customers'),
    path('report_staff_sales/', views.report_staff_sales, name='report_staff_sales'),
    path('api/report_staff_sales/', views.api_report_staff_sales, name='api_report_staff_sales'),
    path('api/export_staff_sales_excel/', views.export_staff_sales_excel, name='export_staff_sales_excel'),
]
