from django.contrib import admin
from .models import (
    UserProfile, RoleGroup, ModulePermission,
    DataPermission, ServicePrice, SystemLog
)

admin.site.register(UserProfile)
admin.site.register(RoleGroup)
admin.site.register(ModulePermission)
admin.site.register(DataPermission)
admin.site.register(ServicePrice)
admin.site.register(SystemLog)
