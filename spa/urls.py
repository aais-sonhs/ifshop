from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path('spa/staff/', views.staff_tbl, name='spa_staff_tbl'),
    path('spa/rooms/', views.room_tbl, name='spa_room_tbl'),
    path('spa/services/', views.service_tbl, name='spa_service_tbl'),
    path('spa/bookings/', views.booking_tbl, name='spa_booking_tbl'),
    path('spa/calendar/', views.booking_calendar, name='spa_booking_calendar'),

    # API: Staff
    path('api/spa/staff/', views.api_get_staff, name='api_spa_staff'),
    path('api/spa/staff/save/', views.api_save_staff, name='api_spa_staff_save'),
    path('api/spa/staff/delete/', views.api_delete_staff, name='api_spa_staff_delete'),

    # API: Room
    path('api/spa/rooms/', views.api_get_rooms, name='api_spa_rooms'),
    path('api/spa/rooms/save/', views.api_save_room, name='api_spa_rooms_save'),
    path('api/spa/rooms/delete/', views.api_delete_room, name='api_spa_rooms_delete'),

    # API: Service
    path('api/spa/services/', views.api_get_services, name='api_spa_services'),
    path('api/spa/services/save/', views.api_save_service, name='api_spa_services_save'),
    path('api/spa/services/delete/', views.api_delete_service, name='api_spa_services_delete'),
    path('api/spa/service_categories/', views.api_get_service_categories, name='api_spa_service_categories'),
    path('api/spa/service_categories/save/', views.api_save_service_category, name='api_spa_service_categories_save'),

    # API: Booking
    path('api/spa/bookings/', views.api_get_bookings, name='api_spa_bookings'),
    path('api/spa/bookings/save/', views.api_save_booking, name='api_spa_bookings_save'),
    path('api/spa/bookings/delete/', views.api_delete_booking, name='api_spa_bookings_delete'),
    path('api/spa/bookings/generate_code/', views.api_generate_booking_code, name='api_spa_bookings_generate_code'),
]
