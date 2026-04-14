
from django.contrib import admin
from django.urls import re_path, include

from config import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.contrib.staticfiles.urls import staticfiles_urlpatterns


# urls
urlpatterns = [
    re_path(r'^', include('authentication.urls')),
    re_path(r'^', include('products.urls')),
    re_path(r'^', include('customers.urls')),
    re_path(r'^', include('orders.urls')),
    re_path(r'^', include('finance.urls')),
    re_path(r'^', include('reports.urls')),
    re_path(r'^', include('system_management.urls')),
    re_path(r'^', include('spa.urls')),
    # PWA: serve sw.js and manifest.json from root for proper scope
    re_path(r'^sw\.js$', serve, {'path': 'sw.js', 'document_root': settings.STATIC_ROOT}),
    re_path(r'^manifest\.json$', serve, {'path': 'manifest.json', 'document_root': settings.STATIC_ROOT}),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    re_path(r'^admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += staticfiles_urlpatterns()
