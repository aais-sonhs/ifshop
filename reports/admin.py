from django.contrib import admin
from .models import StockAlert, StockAlertEmailRecipient

admin.site.register(StockAlert)
admin.site.register(StockAlertEmailRecipient)
