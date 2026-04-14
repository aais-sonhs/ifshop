from django.urls import path
from . import views

urlpatterns = [
    path('customer_tbl/', views.customer_tbl, name='customer_tbl'),
    path('customer_group_tbl/', views.customer_group_tbl, name='customer_group_tbl'),
    path('api/customers/', views.api_get_customers, name='api_get_customers'),
    path('api/customers/save/', views.api_save_customer, name='api_save_customer'),
    path('api/customers/delete/', views.api_delete_customer, name='api_delete_customer'),
    path('api/customer_groups/', views.api_get_customer_groups, name='api_get_customer_groups'),
    path('api/customer_groups/save/', views.api_save_customer_group, name='api_save_customer_group'),
    path('api/customer_groups/delete/', views.api_delete_customer_group, name='api_delete_customer_group'),
    path('api/customers/orders/', views.api_customer_orders, name='api_customer_orders'),
    path('api/customers/upload_avatar/', views.api_upload_customer_avatar, name='api_upload_customer_avatar'),

    # Cafe Tables
    path('cafe_tables/', views.cafe_table_tbl, name='cafe_table_tbl'),
    path('api/cafe_tables/', views.api_get_cafe_tables, name='api_get_cafe_tables'),
    path('api/cafe_tables/save/', views.api_save_cafe_table, name='api_save_cafe_table'),
    path('api/cafe_tables/delete/', views.api_delete_cafe_table, name='api_delete_cafe_table'),
    path('api/cafe_tables/update_status/', views.api_update_table_status, name='api_update_table_status'),

    # Loyalty Points
    path('api/points/history/', views.api_get_point_history, name='api_get_point_history'),
    path('api/points/adjust/', views.api_adjust_points, name='api_adjust_points'),

    # POS
    path('pos/', views.pos_page, name='pos_page'),

    # Dashboard
    path('dashboard/', views.dashboard_page, name='dashboard_page'),
    path('api/dashboard/', views.api_dashboard_data, name='api_dashboard_data'),
    path('api/customers/export_excel/', views.export_customers_excel, name='export_customers_excel'),
]
