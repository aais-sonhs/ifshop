from django.contrib import admin
from .models import FinanceCategory, CashBook, Receipt, Payment

admin.site.register(FinanceCategory)
admin.site.register(CashBook)
admin.site.register(Receipt)
admin.site.register(Payment)
