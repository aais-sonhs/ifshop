from django.urls import path
from . import views

urlpatterns = [
    path('report-sales/', views.report_sales, name='report_sales'),
    path('api/report-sales/', views.api_report_sales, name='api_report_sales'),
    path('report-purchases/', views.report_purchases, name='report_purchases'),
    path('api/report-purchases/', views.api_report_purchases, name='api_report_purchases'),
    path('report-inventory/', views.report_inventory, name='report_inventory'),
    path('api/report-inventory/', views.api_report_inventory, name='api_report_inventory'),
    path('report-finance/', views.report_finance, name='report_finance'),
    path('api/report-finance/', views.api_report_finance, name='api_report_finance'),
    path('report-customers/', views.report_customers, name='report_customers'),
    path('api/report-customers/', views.api_report_customers, name='api_report_customers'),
    path('report-staff-sales/', views.report_staff_sales, name='report_staff_sales'),
    path('api/report-staff-sales/', views.api_report_staff_sales, name='api_report_staff_sales'),
    path('api/export-staff-sales-excel/', views.export_staff_sales_excel, name='export_staff_sales_excel'),
    path('api/export-sales-excel/', views.export_sales_excel, name='export_sales_excel'),
    path('api/export-inventory-excel/', views.export_inventory_excel, name='export_inventory_excel'),
    path('api/export-orders-excel/', views.export_orders_excel, name='export_orders_excel'),
    path('api/export-customers-excel/', views.export_customers_excel, name='export_customers_excel'),
    path('api/export-purchases-excel/', views.export_purchases_excel, name='export_purchases_excel'),
    path('api/export-finance-excel/', views.export_finance_excel, name='export_finance_excel'),
]
