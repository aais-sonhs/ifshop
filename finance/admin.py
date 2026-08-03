from django.contrib import admin
from .models import CashBook, ExpenseClassification, FinanceCategory, Payment, Receipt

admin.site.register(FinanceCategory)
admin.site.register(ExpenseClassification)
admin.site.register(CashBook)
admin.site.register(Receipt)
admin.site.register(Payment)
