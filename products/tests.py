import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from products.models import (
    GoodsReceipt,
    GoodsReceiptItem,
    Product,
    ProductStock,
    StockTransfer,
    StockTransferItem,
    Supplier,
    Warehouse,
)
from system_management.models import Brand, Store, UserProfile


class ProductInventoryFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name='Products Brand')
        cls.store = Store.objects.create(brand=cls.brand, name='Products Store', code='PST')
        cls.user = User.objects.create_user(username='products_user', password='pass123')
        UserProfile.objects.create(user=cls.user, store=cls.store)

        cls.warehouse_a = Warehouse.objects.create(store=cls.store, code='KHO-A1', name='Kho A1')
        cls.warehouse_b = Warehouse.objects.create(store=cls.store, code='KHO-B1', name='Kho B1')
        cls.supplier = Supplier.objects.create(code='SUP-001', name='Supplier Products', created_by=cls.user)
        cls.product = Product.objects.create(
            store=cls.store,
            code='SP-001',
            name='San pham test',
            created_by=cls.user,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_delete_goods_receipt_reverts_stock(self):
        receipt = GoodsReceipt.objects.create(
            code='P00001',
            supplier=self.supplier,
            warehouse=self.warehouse_a,
            receipt_date=date.today(),
            status=1,
            total_amount=Decimal('50'),
            created_by=self.user,
        )
        GoodsReceiptItem.objects.create(
            goods_receipt=receipt,
            product=self.product,
            quantity=Decimal('5'),
            unit_price=Decimal('10'),
            total_price=Decimal('50'),
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse_a, quantity=Decimal('5'))

        response = self.client.post(
            reverse('api_delete_goods_receipt'),
            data=json.dumps({'id': receipt.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())

        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse_a)
        deleted_receipt = GoodsReceipt.all_objects.get(id=receipt.id)
        self.assertEqual(stock.quantity, Decimal('0'))
        self.assertTrue(deleted_receipt.is_deleted)

    def test_save_completed_goods_receipt_moves_stock_to_new_warehouse(self):
        receipt = GoodsReceipt.objects.create(
            code='P00002',
            supplier=self.supplier,
            warehouse=self.warehouse_a,
            receipt_date=date.today(),
            status=1,
            total_amount=Decimal('50'),
            created_by=self.user,
        )
        GoodsReceiptItem.objects.create(
            goods_receipt=receipt,
            product=self.product,
            quantity=Decimal('5'),
            unit_price=Decimal('10'),
            total_price=Decimal('50'),
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse_a, quantity=Decimal('5'))

        response = self.client.post(
            reverse('api_save_goods_receipt'),
            data=json.dumps({
                'id': receipt.id,
                'code': receipt.code,
                'supplier_id': self.supplier.id,
                'warehouse_id': self.warehouse_b.id,
                'receipt_date': date.today().isoformat(),
                'status': 1,
                'items': [{
                    'product_id': self.product.id,
                    'quantity': 5,
                    'unit_price': 10,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())

        stock_a = ProductStock.objects.get(product=self.product, warehouse=self.warehouse_a)
        stock_b = ProductStock.objects.get(product=self.product, warehouse=self.warehouse_b)
        self.assertEqual(stock_a.quantity, Decimal('0'))
        self.assertEqual(stock_b.quantity, Decimal('5'))

    def test_delete_completed_stock_transfer_reverts_stock(self):
        transfer = StockTransfer.objects.create(
            code='CK-001',
            from_warehouse=self.warehouse_a,
            to_warehouse=self.warehouse_b,
            transfer_date=date.today(),
            status=2,
            created_by=self.user,
        )
        StockTransferItem.objects.create(
            transfer=transfer,
            product=self.product,
            quantity=Decimal('3'),
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse_a, quantity=Decimal('7'))
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse_b, quantity=Decimal('3'))

        response = self.client.post(
            reverse('api_delete_stock_transfer'),
            data=json.dumps({'id': transfer.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())

        stock_a = ProductStock.objects.get(product=self.product, warehouse=self.warehouse_a)
        stock_b = ProductStock.objects.get(product=self.product, warehouse=self.warehouse_b)
        deleted_transfer = StockTransfer.all_objects.get(id=transfer.id)
        self.assertEqual(stock_a.quantity, Decimal('10'))
        self.assertEqual(stock_b.quantity, Decimal('0'))
        self.assertTrue(deleted_transfer.is_deleted)
