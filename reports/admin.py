from django.contrib import admin
from .models import DailyEmailReportRecipient, StockAlert, StockAlertEmailRecipient

admin.site.register(StockAlert)
admin.site.register(StockAlertEmailRecipient)
admin.site.register(DailyEmailReportRecipient)
