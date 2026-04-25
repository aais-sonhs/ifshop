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
    StockCheck,
    StockCheckItem,
    StockTransfer,
    StockTransferItem,
    Supplier,
    Warehouse,
)
from system_management.models import Brand, BusinessConfig, Store, UserProfile


class ProductInventoryFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='products_owner', password='pass123')
        cls.brand = Brand.objects.create(name='Products Brand', owner=cls.owner)
        cls.store = Store.objects.create(brand=cls.brand, name='Products Store', code='PST')
        cls.other_store = Store.objects.create(brand=cls.brand, name='Other Products Store', code='OPS')
        cls.user = User.objects.create_user(username='products_user', password='pass123')
        UserProfile.objects.create(user=cls.user, store=cls.store)
        cls.other_user = User.objects.create_user(username='other_products_user', password='pass123')
        UserProfile.objects.create(user=cls.other_user, store=cls.other_store)

        cls.warehouse_a = Warehouse.objects.create(store=cls.store, code='KHO-A1', name='Kho A1')
        cls.warehouse_b = Warehouse.objects.create(store=cls.store, code='KHO-B1', name='Kho B1')
        cls.other_warehouse = Warehouse.objects.create(store=cls.other_store, code='KHO-OTHER', name='Kho khác')
        cls.supplier = Supplier.objects.create(code='SUP-001', name='Supplier Products', created_by=cls.user)
        cls.product = Product.objects.create(
            store=cls.store,
            code='SP-001',
            name='San pham test',
            created_by=cls.user,
        )
        cls.other_product = Product.objects.create(
            store=cls.other_store,
            code='SP-OTHER-001',
            name='San pham store khac',
            created_by=cls.other_user,
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

    def test_goods_receipt_list_uses_total_item_quantity(self):
        receipt = GoodsReceipt.objects.create(
            code='P00003',
            supplier=self.supplier,
            warehouse=self.warehouse_a,
            receipt_date=date.today(),
            status=1,
            total_amount=Decimal('75'),
            created_by=self.user,
        )
        GoodsReceiptItem.objects.create(
            goods_receipt=receipt,
            product=self.product,
            quantity=Decimal('5'),
            unit_price=Decimal('10'),
            total_price=Decimal('50'),
        )
        GoodsReceiptItem.objects.create(
            goods_receipt=receipt,
            product=self.product,
            quantity=Decimal('2.5'),
            unit_price=Decimal('10'),
            total_price=Decimal('25'),
        )

        response = self.client.get(reverse('api_get_goods_receipts'))

        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.json()['data'] if item['id'] == receipt.id)
        self.assertEqual(row['items_count'], 2)
        self.assertEqual(row['total_quantity'], 7.5)
        self.assertEqual(sum(item['quantity'] for item in row['items']), 7.5)

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

    def test_save_completed_stock_transfer_rejects_negative_source_stock_when_disabled(self):
        BusinessConfig.objects.create(
            brand=self.brand,
            business_name='Transfer negative disabled',
            opt_allow_negative_stock=False,
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse_a, quantity=Decimal('0'))

        response = self.client.post(
            reverse('api_save_stock_transfer'),
            data=json.dumps({
                'code': 'CK-NEG-STOCK',
                'from_warehouse_id': self.warehouse_a.id,
                'to_warehouse_id': self.warehouse_b.id,
                'transfer_date': date.today().isoformat(),
                'status': 2,
                'items': [{
                    'product_id': self.product.id,
                    'quantity': 1,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Tồn kho không đủ', payload['message'])
        self.assertFalse(StockTransfer.objects.filter(code='CK-NEG-STOCK').exists())

    def test_save_stock_transfer_invalid_item_does_not_revert_existing_stock(self):
        transfer = StockTransfer.objects.create(
            code='CK-ROLLBACK',
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
            reverse('api_save_stock_transfer'),
            data=json.dumps({
                'id': transfer.id,
                'code': transfer.code,
                'from_warehouse_id': self.warehouse_a.id,
                'to_warehouse_id': self.warehouse_b.id,
                'transfer_date': date.today().isoformat(),
                'status': 2,
                'items': [{
                    'product_id': self.other_product.id,
                    'quantity': 1,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('sản phẩm', payload['message'].lower())

        stock_a = ProductStock.objects.get(product=self.product, warehouse=self.warehouse_a)
        stock_b = ProductStock.objects.get(product=self.product, warehouse=self.warehouse_b)
        self.assertEqual(stock_a.quantity, Decimal('7'))
        self.assertEqual(stock_b.quantity, Decimal('3'))
        self.assertEqual(list(transfer.items.values_list('product_id', 'quantity')), [(self.product.id, Decimal('3.00'))])

    def test_save_stock_check_uses_decimal_quantities(self):
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse_a, quantity=Decimal('5'))

        response = self.client.post(
            reverse('api_save_stock_check'),
            data=json.dumps({
                'code': 'KK-DECIMAL',
                'warehouse_id': self.warehouse_a.id,
                'check_date': date.today().isoformat(),
                'status': 1,
                'items': [{
                    'product_id': self.product.id,
                    'actual_quantity': '3.5',
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())
        stock_check = StockCheck.objects.get(code='KK-DECIMAL')
        item = StockCheckItem.objects.get(stock_check=stock_check)
        self.assertEqual(item.system_quantity, Decimal('5.00'))
        self.assertEqual(item.actual_quantity, Decimal('3.50'))
        self.assertEqual(item.difference, Decimal('-1.50'))

    def test_delete_goods_receipt_rejects_negative_stock_when_disabled(self):
        BusinessConfig.objects.create(
            brand=self.brand,
            business_name='Receipt delete negative disabled',
            opt_allow_negative_stock=False,
        )
        receipt = GoodsReceipt.objects.create(
            code='P00004',
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
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse_a, quantity=Decimal('0'))

        response = self.client.post(
            reverse('api_delete_goods_receipt'),
            data=json.dumps({'id': receipt.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Tồn kho không đủ', payload['message'])

        receipt.refresh_from_db()
        self.assertFalse(receipt.is_deleted)

    def test_save_goods_receipt_rejects_foreign_warehouse(self):
        response = self.client.post(
            reverse('api_save_goods_receipt'),
            data=json.dumps({
                'code': 'P-FOREIGN-WH',
                'supplier_id': self.supplier.id,
                'warehouse_id': self.other_warehouse.id,
                'receipt_date': date.today().isoformat(),
                'status': 1,
                'items': [{
                    'product_id': self.product.id,
                    'quantity': 1,
                    'unit_price': 10,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Kho nhập', payload['message'])
        self.assertFalse(GoodsReceipt.objects.filter(code='P-FOREIGN-WH').exists())

    def test_save_goods_receipt_rejects_foreign_product(self):
        response = self.client.post(
            reverse('api_save_goods_receipt'),
            data=json.dumps({
                'code': 'P-FOREIGN-PRODUCT',
                'supplier_id': self.supplier.id,
                'warehouse_id': self.warehouse_a.id,
                'receipt_date': date.today().isoformat(),
                'status': 1,
                'items': [{
                    'product_id': self.other_product.id,
                    'quantity': 1,
                    'unit_price': 10,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('sản phẩm', payload['message'].lower())
        self.assertFalse(GoodsReceipt.objects.filter(code='P-FOREIGN-PRODUCT').exists())

    def test_save_purchase_order_rejects_foreign_warehouse(self):
        response = self.client.post(
            reverse('api_save_purchase_order'),
            data=json.dumps({
                'code': 'PO-FOREIGN-WH',
                'supplier_id': self.supplier.id,
                'warehouse_id': self.other_warehouse.id,
                'order_date': date.today().isoformat(),
                'status': 0,
                'items': [{
                    'product_id': self.product.id,
                    'quantity': 1,
                    'unit_price': 10,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Kho nhập', payload['message'])

    def test_regular_staff_cannot_save_supplier(self):
        response = self.client.post(
            reverse('api_save_supplier'),
            data=json.dumps({
                'code': 'SUP-STAFF',
                'name': 'Supplier Staff',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['status'], 'error')

    def test_brand_owner_cannot_save_receipt_with_product_from_other_store_than_warehouse(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('api_save_goods_receipt'),
            data=json.dumps({
                'code': 'P-CROSS-STORE-PRODUCT',
                'supplier_id': self.supplier.id,
                'warehouse_id': self.warehouse_a.id,
                'receipt_date': date.today().isoformat(),
                'status': 1,
                'items': [{
                    'product_id': self.other_product.id,
                    'quantity': 1,
                    'unit_price': 10,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('không cùng cửa hàng', payload['message'])
        self.assertFalse(GoodsReceipt.objects.filter(code='P-CROSS-STORE-PRODUCT').exists())

    def test_brand_owner_cannot_transfer_between_different_store_warehouses(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('api_save_stock_transfer'),
            data=json.dumps({
                'code': 'CK-CROSS-STORE-WH',
                'from_warehouse_id': self.warehouse_a.id,
                'to_warehouse_id': self.other_warehouse.id,
                'transfer_date': date.today().isoformat(),
                'status': 2,
                'items': [{
                    'product_id': self.product.id,
                    'quantity': 1,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('cùng cửa hàng', payload['message'])
        self.assertFalse(StockTransfer.objects.filter(code='CK-CROSS-STORE-WH').exists())
