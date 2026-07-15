from django.contrib import admin
from .models import Customer, CustomerAddress, CustomerGroup

admin.site.register(Customer)
admin.site.register(CustomerAddress)
admin.site.register(CustomerGroup)
