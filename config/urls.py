
from django.contrib import admin
from django.urls import re_path, include

from config import settings
from django.views.static import serve
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.contrib.staticfiles.views import serve as staticfiles_serve


# urls
urlpatterns = [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += [
        re_path(r'^sw\.js$', staticfiles_serve, {'path': 'sw.js'}),
        re_path(r'^manifest\.json$', staticfiles_serve, {'path': 'manifest.json'}),
    ]
else:
    urlpatterns += [
        re_path(r'^sw\.js$', serve, {'path': 'sw.js', 'document_root': settings.STATIC_ROOT}),
        re_path(r'^manifest\.json$', serve, {'path': 'manifest.json', 'document_root': settings.STATIC_ROOT}),
        re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    ]

urlpatterns += [
    re_path(r'^', include('authentication.urls')),
    re_path(r'^', include('products.urls')),
    re_path(r'^', include('customers.urls')),
    re_path(r'^', include('orders.urls')),
    re_path(r'^', include('finance.urls')),
    re_path(r'^', include('reports.urls')),
    re_path(r'^', include('system_management.urls')),
    re_path(r'^', include('spa.urls')),
    re_path(r'^admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
