from django.urls import path
from . import views

urlpatterns = [
    path('user-management-tbl/', views.user_management_tbl, name='user_management_tbl'),
    path('role-group-tbl/', views.role_group_tbl, name='role_group_tbl'),
    path('permission-tbl/', views.permission_tbl, name='permission_tbl'),
    path('category-tbl/', views.category_tbl, name='category_tbl'),
    path('service-price-tbl/', views.service_price_tbl, name='service_price_tbl'),
    path('api/service-prices/', views.api_get_service_prices, name='api_get_service_prices'),
    path('api/service-prices/save/', views.api_save_service_price, name='api_save_service_price'),
    path('api/service-prices/delete/', views.api_delete_service_price, name='api_delete_service_price'),
    path('api/users/', views.api_get_users, name='api_get_users'),
    path('api/users/save/', views.api_save_user, name='api_save_user'),
    path('api/users/delete/', views.api_delete_user, name='api_delete_user'),
    path('api/stores-for-user/', views.api_get_stores_for_user, name='api_get_stores_for_user'),
    # Role Group
    path('api/role-groups/', views.api_get_role_groups, name='api_get_role_groups'),
    path('api/role-groups/save/', views.api_save_role_group, name='api_save_role_group'),
    path('api/role-groups/delete/', views.api_delete_role_group, name='api_delete_role_group'),
    path('api/role-groups/assign/', views.api_assign_role_group, name='api_assign_role_group'),
    # Printer settings
    path('printer-setting-tbl/', views.printer_setting_tbl, name='printer_setting_tbl'),
    path('api/printers/', views.api_get_printers, name='api_get_printers'),
    path('api/printers/save/', views.api_save_printer, name='api_save_printer'),
    path('api/printers/delete/', views.api_delete_printer, name='api_delete_printer'),
    path('api/printers/test/', views.api_test_printer, name='api_test_printer'),
    path('api/printers/direct-print/', views.api_direct_print, name='api_direct_print'),
    # Business Config
    path('business-config/', views.business_config_tbl, name='business_config_tbl'),
    path('setting/quotation/', views.setting_quotation, name='setting_quotation'),
    path('setting/order/', views.setting_order, name='setting_order'),
    path('api/business-config/', views.api_get_business_config, name='api_get_business_config'),
    path('api/business-config/save/', views.api_save_business_config, name='api_save_business_config'),
    # Brand & Store
    path('brand-tbl/', views.brand_tbl, name='brand_tbl'),
    path('api/brands/', views.api_get_brands, name='api_get_brands'),
    path('api/brands/save/', views.api_save_brand, name='api_save_brand'),
    path('api/brands/delete/', views.api_delete_brand, name='api_delete_brand'),
    path('api/stores/save/', views.api_save_store, name='api_save_store'),
    path('api/stores/delete/', views.api_delete_store, name='api_delete_store'),
    # Profile
    path('api/profile/', views.api_get_my_profile, name='api_get_my_profile'),
    path('api/profile/change-password/', views.api_change_my_password, name='api_change_my_password'),
    path('api/profile/upload-avatar/', views.api_upload_my_avatar, name='api_upload_my_avatar'),
]
