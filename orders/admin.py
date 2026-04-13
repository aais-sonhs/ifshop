from django.contrib import admin
from .models import (
    Quotation, QuotationItem, Order, OrderItem,
    OrderReturn, OrderReturnItem, Packaging
)

admin.site.register(Quotation)
admin.site.register(QuotationItem)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(OrderReturn)
admin.site.register(OrderReturnItem)
admin.site.register(Packaging)
