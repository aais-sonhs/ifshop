from django.contrib import admin
from .models import (
    Supplier, ProductCategory, Warehouse, Product, ProductStock,
    PurchaseOrder, PurchaseOrderItem, GoodsReceipt, GoodsReceiptItem,
    StockCheck, StockCheckItem, StockTransfer, StockTransferItem, CostAdjustment
)

admin.site.register(Supplier)
admin.site.register(ProductCategory)
admin.site.register(Warehouse)
admin.site.register(Product)
admin.site.register(ProductStock)
admin.site.register(PurchaseOrder)
admin.site.register(PurchaseOrderItem)
admin.site.register(GoodsReceipt)
admin.site.register(GoodsReceiptItem)
admin.site.register(StockCheck)
admin.site.register(StockCheckItem)
admin.site.register(StockTransfer)
admin.site.register(StockTransferItem)
admin.site.register(CostAdjustment)
