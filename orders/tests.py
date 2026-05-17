import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from customers.models import Customer
from finance.models import CashBook, Payment, PaymentMethodOption, Receipt
from orders.models import Order, OrderItem, OrderReturn, Quotation
from products.models import Product, ProductStock, Warehouse
from system_management.models import Brand, BusinessConfig, Store, UserProfile


class OrderRiskFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='order_owner', password='pass123')
        cls.brand = Brand.objects.create(name='Test Brand', owner=cls.owner)
        cls.store = Store.objects.create(brand=cls.brand, name='Store A', code='STA')
        cls.other_store = Store.objects.create(brand=cls.brand, name='Store B', code='STB')

        cls.user = User.objects.create_user(username='seller_a', password='pass123')
        cls.other_user = User.objects.create_user(username='seller_b', password='pass123')
        UserProfile.objects.create(user=cls.user, store=cls.store)
        UserProfile.objects.create(user=cls.other_user, store=cls.other_store)

        cls.customer = Customer.objects.create(
            store=cls.store,
            code='KH001',
            name='Customer A',
            created_by=cls.user,
        )
        cls.other_customer = Customer.objects.create(
            store=cls.other_store,
            code='KH002',
            name='Customer B',
            created_by=cls.other_user,
        )

        cls.warehouse = Warehouse.objects.create(store=cls.store, code='KHO-A', name='Kho A')
        cls.other_warehouse = Warehouse.objects.create(
            store=cls.other_store,
            code='KHO-B',
            name='Kho B',
        )
        cls.product = Product.objects.create(
            store=cls.store,
            code='SP-ORDER-001',
            name='Sản phẩm test đơn hàng',
            created_by=cls.user,
        )
        cls.other_product = Product.objects.create(
            store=cls.other_store,
            code='SP-ORDER-OTHER',
            name='Sản phẩm store khác',
            created_by=cls.other_user,
        )
        cls.cashbook = CashBook.objects.create(
            name='Tiền mặt test đơn hàng',
            balance=1000000,
        )
        cls.payment_method = PaymentMethodOption.objects.create(
            code='TMORDERTEST',
            name='Tiền mặt test',
            legacy_type=1,
            default_cash_book=cls.cashbook,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _create_quotation(self, code, store=None, customer=None, created_by=None, status=3):
        return Quotation.objects.create(
            code=code,
            store=store or self.store,
            customer=customer or self.customer,
            status=status,
            total_amount=100,
            final_amount=100,
            quotation_date=date.today(),
            created_by=created_by or self.user,
        )

    def _create_order(
        self,
        code,
        quotation=None,
        store=None,
        customer=None,
        warehouse=None,
        created_by=None,
        status=1,
    ):
        store = store or self.store
        return Order.objects.create(
            code=code,
            store=store,
            quotation=quotation,
            customer=customer or self.customer,
            warehouse=warehouse or self.warehouse,
            status=status,
            total_amount=100,
            final_amount=100,
            order_date=date.today(),
            created_by=created_by or self.user,
        )

    def test_save_order_allows_status_change_when_draft_receipt_exists(self):
        order = self._create_order(code='DH-PAID-001', status=0)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=50,
            total_price=100,
        )
        Receipt.objects.create(
            code='PT-PAID-001',
            store=self.store,
            customer=self.customer,
            order=order,
            amount=100,
            receipt_date=date.today(),
            status=1,
            description='Phiếu thu thủ công',
            created_by=self.user,
        )

        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'id': order.id,
                'code': order.code,
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': order.order_date.isoformat(),
                'discount_amount': 0,
                'shipping_fee': 0,
                'status': 1,
                'note': '',
                'tags': '',
                'pay_mode': 'none',
                'payment_amount': 0,
                'payment_lines': [],
                'items': [{
                    'product_id': self.product.id,
                    'variant_id': None,
                    'quantity': 2,
                    'unit_price': 50,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())
        self.assertEqual(payload['order_status'], 1)
        self.assertEqual(payload['payment_status'], 2)

        order.refresh_from_db()
        self.assertEqual(order.status, 1)
        self.assertEqual(order.final_amount, 100)

    def test_save_order_allows_financial_edit_before_completion_when_receipt_exists(self):
        order = self._create_order(code='DH-PAID-EDIT-001', status=0)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=100,
            total_price=100,
        )
        Receipt.objects.create(
            code='PT-PAID-EDIT-001',
            store=self.store,
            customer=self.customer,
            order=order,
            amount=100,
            receipt_date=date.today(),
            status=1,
            description='Phiếu thu thủ công',
            created_by=self.user,
        )

        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'id': order.id,
                'code': order.code,
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': order.order_date.isoformat(),
                'status': 1,
                'discount_amount': 10,
                'shipping_fee': 0,
                'note': '',
                'tags': '',
                'pay_mode': 'none',
                'payment_amount': 0,
                'payment_lines': [],
                'items': [{
                    'product_id': self.product.id,
                    'variant_id': None,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        order.refresh_from_db()
        self.assertEqual(order.status, 1)
        self.assertEqual(order.discount_amount, 10)
        self.assertEqual(order.final_amount, 90)
        self.assertEqual(order.payment_status, 2)

    def test_save_order_clamps_final_amount_to_zero_when_discount_exceeds_total(self):
        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'code': 'DH-DISCOUNT-CLAMP',
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': date.today().isoformat(),
                'discount_amount': 150,
                'shipping_fee': 0,
                'status': 0,
                'note': '',
                'tags': '',
                'pay_mode': 'none',
                'payment_amount': 0,
                'payment_lines': [],
                'items': [{
                    'product_id': self.product.id,
                    'variant_id': None,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        order = Order.objects.get(id=payload['order_id'])
        self.assertEqual(float(order.total_amount), 100.0)
        self.assertEqual(float(order.final_amount), 0.0)
        self.assertEqual(order.payment_status, 2)

    def test_partial_payment_converts_quote_status_to_order(self):
        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'code': 'DH-PARTIAL-TO-ORDER',
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': date.today().isoformat(),
                'discount_amount': 0,
                'shipping_fee': 0,
                'status': 0,
                'note': '',
                'tags': '',
                'pay_mode': 'partial',
                'payment_amount': 40,
                'payment_lines': [{'amount': 40, 'payment_method': 2}],
                'items': [{
                    'product_id': self.product.id,
                    'variant_id': None,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        order = Order.objects.get(id=payload['order_id'])
        self.assertEqual(order.status, 1)
        self.assertEqual(order.payment_status, 1)
        self.assertEqual(float(order.paid_amount), 40.0)

    def test_export_with_full_payment_auto_completes_and_deducts_stock_once(self):
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=5)

        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'code': 'DH-EXPORT-PAID',
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': date.today().isoformat(),
                'discount_amount': 0,
                'shipping_fee': 0,
                'status': 4,
                'note': '',
                'tags': '',
                'pay_mode': 'full',
                'payment_amount': 100,
                'payment_lines': [{'amount': 100, 'payment_method': 2}],
                'items': [{
                    'product_id': self.product.id,
                    'variant_id': None,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        order = Order.objects.get(id=payload['order_id'])
        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(order.status, 5)
        self.assertEqual(order.payment_status, 2)
        self.assertEqual(float(stock.quantity), 4.0)

    def test_new_order_cannot_start_completed_even_when_fully_paid(self):
        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'code': 'DH-COMPLETE-WITHOUT-EXPORT',
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': date.today().isoformat(),
                'discount_amount': 0,
                'shipping_fee': 0,
                'status': 5,
                'note': '',
                'tags': '',
                'pay_mode': 'full',
                'payment_amount': 100,
                'payment_lines': [{'amount': 100, 'payment_method': 2}],
                'items': [{
                    'product_id': self.product.id,
                    'variant_id': None,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('xuất kho', payload['message'])
        self.assertFalse(Order.objects.filter(code='DH-COMPLETE-WITHOUT-EXPORT').exists())

    def test_exported_order_cannot_complete_until_fully_paid(self):
        order = self._create_order(code='DH-EXPORT-PARTIAL', status=4)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=100,
            total_price=100,
        )
        Receipt.objects.create(
            code='PT-EXPORT-PARTIAL',
            store=self.store,
            customer=self.customer,
            order=order,
            amount=40,
            receipt_date=date.today(),
            status=1,
            description='Thu một phần',
            created_by=self.user,
        )

        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'id': order.id,
                'code': order.code,
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': order.order_date.isoformat(),
                'discount_amount': 0,
                'shipping_fee': 0,
                'status': 5,
                'note': '',
                'tags': '',
                'pay_mode': 'none',
                'payment_amount': 0,
                'payment_lines': [],
                'items': [{
                    'product_id': self.product.id,
                    'variant_id': None,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('thanh toán đủ', payload['message'])

        order.refresh_from_db()
        self.assertEqual(order.status, 4)

    def test_save_order_allows_below_cost_with_warning(self):
        self.product.cost_price = 150
        self.product.import_price = 150
        self.product.save(update_fields=['cost_price', 'import_price'])

        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'code': 'DH-BELOW-COST-WARN',
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': date.today().isoformat(),
                'discount_amount': 0,
                'shipping_fee': 0,
                'status': 1,
                'note': '',
                'tags': '',
                'pay_mode': 'none',
                'payment_amount': 0,
                'payment_lines': [],
                'items': [{
                    'product_id': self.product.id,
                    'variant_id': None,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())
        self.assertIn('Cảnh báo', payload['message'])

        order = Order.objects.get(code='DH-BELOW-COST-WARN')
        self.assertTrue(order.below_listed_price_warning)
        self.assertTrue(order.items.first().is_below_listed)

    def test_completed_order_note_can_be_updated(self):
        order = self._create_order(code='DH-COMPLETE-NOTE', status=5)

        response = self.client.post(
            reverse('api_update_order_note'),
            data=json.dumps({'id': order.id, 'note': 'Ghi chú sau hoàn thành'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        order.refresh_from_db()
        self.assertEqual(order.note, 'Ghi chú sau hoàn thành')

    def test_canceled_order_note_remains_locked(self):
        order = self._create_order(code='DH-CANCEL-NOTE', status=6)

        response = self.client.post(
            reverse('api_update_order_note'),
            data=json.dumps({'id': order.id, 'note': 'Không được sửa'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Hủy', payload['message'])

        order.refresh_from_db()
        self.assertNotEqual(order.note, 'Không được sửa')

    def test_cancel_order_reopens_linked_quotation(self):
        quotation = self._create_quotation(code='BG-CANCEL-001')
        order = self._create_order(code='DH-CANCEL-001', quotation=quotation)

        response = self.client.post(
            reverse('api_cancel_order'),
            data=json.dumps({'id': order.id, 'reason': 'Kiểm tra test'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')

        order.refresh_from_db()
        quotation.refresh_from_db()
        self.assertEqual(order.status, 6)
        self.assertEqual(order.payment_status, 0)
        self.assertEqual(order.paid_amount, 0)
        self.assertEqual(quotation.status, 2)

    def test_delete_order_soft_deletes_and_reopens_linked_quotation(self):
        quotation = self._create_quotation(code='BG-DELETE-001')
        order = self._create_order(code='DH-DELETE-001', quotation=quotation)

        response = self.client.post(
            reverse('api_delete_order'),
            data=json.dumps({'id': order.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')

        deleted_order = Order.all_objects.get(id=order.id)
        quotation.refresh_from_db()
        self.assertTrue(deleted_order.is_deleted)
        self.assertEqual(quotation.status, 2)

    def test_bulk_cancel_reopens_linked_quotation(self):
        quotation = self._create_quotation(code='BG-BULK-001')
        order = self._create_order(code='DH-BULK-001', quotation=quotation)

        response = self.client.post(
            reverse('api_bulk_cancel_orders'),
            data=json.dumps({'ids': [order.id], 'reason': 'Bulk test'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')

        order.refresh_from_db()
        quotation.refresh_from_db()
        self.assertEqual(order.status, 6)
        self.assertEqual(quotation.status, 2)

    def test_bulk_collect_returns_total_collected_for_reconciliation(self):
        first_order = self._create_order(code='DH-BULK-COLLECT-001')
        second_order = self._create_order(code='DH-BULK-COLLECT-002')
        second_order.final_amount = 150
        second_order.save(update_fields=['final_amount'])
        Receipt.objects.create(
            code='PT-BULK-COLLECT-PARTIAL',
            store=self.store,
            customer=self.customer,
            order=second_order,
            amount=50,
            receipt_date=date.today(),
            status=1,
            description='Thu một phần',
            created_by=self.user,
        )

        response = self.client.post(
            reverse('api_bulk_collect_orders'),
            data=json.dumps({'ids': [first_order.id, second_order.id], 'payment_method': 2}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())
        self.assertEqual(payload['collected_count'], 2)
        self.assertEqual(payload['total_collected'], 200.0)
        self.assertIn('Tổng đã thu', payload['message'])

        first_order.refresh_from_db()
        second_order.refresh_from_db()
        self.assertEqual(float(first_order.paid_amount), 100.0)
        self.assertEqual(float(second_order.paid_amount), 150.0)
        self.assertEqual(first_order.payment_status, 2)
        self.assertEqual(second_order.payment_status, 2)

    def test_store_scope_blocks_foreign_order_detail(self):
        quotation = self._create_quotation(
            code='BG-OTHER-001',
            store=self.other_store,
            customer=self.other_customer,
            created_by=self.other_user,
        )
        other_order = self._create_order(
            code='DH-OTHER-001',
            quotation=quotation,
            store=self.other_store,
            customer=self.other_customer,
            warehouse=self.other_warehouse,
            created_by=self.other_user,
        )

        response = self.client.get(reverse('api_get_order_detail'), {'id': other_order.id})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['message'], 'Không tìm thấy')

    def test_save_order_rejects_foreign_warehouse(self):
        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'code': 'DH-FOREIGN-WH',
                'customer_id': self.customer.id,
                'warehouse_id': self.other_warehouse.id,
                'order_date': date.today().isoformat(),
                'status': 0,
                'items': [{
                    'product_id': self.product.id,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Kho xuất', payload['message'])
        self.assertFalse(Order.objects.filter(code='DH-FOREIGN-WH').exists())

    def test_save_order_rejects_foreign_product(self):
        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'code': 'DH-FOREIGN-PRODUCT',
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': date.today().isoformat(),
                'status': 0,
                'items': [{
                    'product_id': self.other_product.id,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('sản phẩm', payload['message'].lower())
        self.assertFalse(Order.objects.filter(code='DH-FOREIGN-PRODUCT').exists())

    def test_save_exported_order_rejects_negative_stock_when_disabled(self):
        BusinessConfig.objects.create(
            brand=self.brand,
            business_name='Negative stock disabled',
            opt_allow_negative_stock=False,
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=0)

        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'code': 'DH-NEG-STOCK',
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': date.today().isoformat(),
                'status': 4,
                'items': [{
                    'product_id': self.product.id,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Tồn kho không đủ', payload['message'])
        self.assertFalse(Order.objects.filter(code='DH-NEG-STOCK').exists())

    def test_pos_checkout_rejects_negative_stock_when_disabled(self):
        BusinessConfig.objects.create(
            brand=self.brand,
            business_name='POS negative stock disabled',
            opt_allow_negative_stock=False,
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=0)

        response = self.client.post(
            reverse('api_pos_checkout'),
            data=json.dumps({
                'items': [{
                    'product_id': self.product.id,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
                'discount_amount': 0,
                'paid_amount': 100,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Tồn kho không đủ', payload['message'])
        self.assertFalse(Order.objects.filter(code__startswith='POS-').exists())

    def test_quotation_detail_blocks_foreign_quotation(self):
        quotation = self._create_quotation(
            code='BG-FOREIGN-DETAIL',
            store=self.other_store,
            customer=self.other_customer,
            created_by=self.other_user,
        )

        response = self.client.get(reverse('api_get_quotation_detail'), {'id': quotation.id})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['message'], 'Không tìm thấy')

    def test_brand_owner_cannot_save_order_with_product_from_other_store_than_warehouse(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'code': 'DH-CROSS-STORE-PRODUCT',
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': date.today().isoformat(),
                'status': 0,
                'items': [{
                    'product_id': self.other_product.id,
                    'quantity': 1,
                    'unit_price': 100,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('không cùng cửa hàng', payload['message'])
        self.assertFalse(Order.objects.filter(code='DH-CROSS-STORE-PRODUCT').exists())

    def test_save_order_return_requires_order_and_syncs_order_fields(self):
        order = self._create_order(code='DH-RETURN-001', status=5)

        missing_order_response = self.client.post(
            reverse('api_save_order_return'),
            data=json.dumps({
                'code': 'TH-RETURN-001',
                'return_date': date.today().isoformat(),
                'total_refund': 50,
                'status': 2,
            }),
            content_type='application/json',
        )

        self.assertEqual(missing_order_response.status_code, 200)
        missing_payload = missing_order_response.json()
        self.assertEqual(missing_payload['status'], 'error')
        self.assertIn('đơn hàng gốc', missing_payload['message'])

        response = self.client.post(
            reverse('api_save_order_return'),
            data=json.dumps({
                'code': 'TH-RETURN-002',
                'order_id': order.id,
                'return_date': date.today().isoformat(),
                'total_refund': 50,
                'status': 2,
                'reason': 'Khách đổi ý',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        order_return = OrderReturn.objects.get(code='TH-RETURN-002')
        self.assertEqual(order_return.order_id, order.id)
        self.assertEqual(order_return.customer_id, order.customer_id)
        self.assertEqual(order_return.warehouse_id, order.warehouse_id)
        self.assertEqual(order_return.status, 2)
        self.assertIn('PC-TH-RETURN-002', payload['message'])

        refund_payment = Payment.objects.get(reference=f'ORDER_RETURN:{order_return.id}')
        self.assertEqual(refund_payment.code, 'PC-TH-RETURN-002')
        self.assertEqual(refund_payment.customer_id, order.customer_id)
        self.assertEqual(refund_payment.payment_method_option_id, self.payment_method.id)
        self.assertEqual(float(refund_payment.amount), 50.0)
        self.cashbook.refresh_from_db()
        self.assertEqual(float(self.cashbook.balance), 999950.0)

    def test_order_return_list_keeps_legacy_orphan_in_scope(self):
        orphan_return = OrderReturn.objects.create(
            code='TH-LEGACY-001',
            customer=self.customer,
            warehouse=self.warehouse,
            status=0,
            total_refund=25,
            return_date=date.today(),
            created_by=self.user,
        )
        OrderReturn.objects.create(
            code='TH-LEGACY-OTHER',
            customer=self.other_customer,
            warehouse=self.other_warehouse,
            status=0,
            total_refund=30,
            return_date=date.today(),
            created_by=self.other_user,
        )

        response = self.client.get(reverse('api_get_order_returns'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload['data']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], orphan_return.id)
        self.assertEqual(rows[0]['order'], '(Thiếu đơn gốc)')

    def test_save_order_return_allows_linking_legacy_orphan(self):
        order = self._create_order(code='DH-RETURN-LEGACY', status=5)
        orphan_return = OrderReturn.objects.create(
            code='TH-LEGACY-EDIT',
            customer=self.customer,
            warehouse=self.warehouse,
            status=0,
            total_refund=40,
            return_date=date.today(),
            created_by=self.user,
        )

        response = self.client.post(
            reverse('api_save_order_return'),
            data=json.dumps({
                'id': orphan_return.id,
                'code': orphan_return.code,
                'order_id': order.id,
                'return_date': date.today().isoformat(),
                'total_refund': 40,
                'status': 2,
                'reason': 'Bổ sung đơn gốc',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        orphan_return.refresh_from_db()
        self.assertEqual(orphan_return.order_id, order.id)
        self.assertEqual(orphan_return.customer_id, order.customer_id)
        self.assertEqual(orphan_return.warehouse_id, order.warehouse_id)
        self.assertEqual(orphan_return.status, 2)

    def test_save_order_return_updates_refund_payment_and_restores_cashbook_on_cancel(self):
        order = self._create_order(code='DH-RETURN-UPDATE', status=5)

        create_response = self.client.post(
            reverse('api_save_order_return'),
            data=json.dumps({
                'code': 'TH-RETURN-UPDATE',
                'order_id': order.id,
                'return_date': date.today().isoformat(),
                'total_refund': 50,
                'status': 2,
                'payment_method_option_id': self.payment_method.id,
            }),
            content_type='application/json',
        )
        self.assertEqual(create_response.json()['status'], 'ok', msg=create_response.content.decode())
        order_return = OrderReturn.objects.get(code='TH-RETURN-UPDATE')

        update_response = self.client.post(
            reverse('api_save_order_return'),
            data=json.dumps({
                'id': order_return.id,
                'code': order_return.code,
                'order_id': order.id,
                'return_date': date.today().isoformat(),
                'total_refund': 80,
                'status': 2,
                'payment_method_option_id': self.payment_method.id,
            }),
            content_type='application/json',
        )
        self.assertEqual(update_response.json()['status'], 'ok', msg=update_response.content.decode())

        refund_payment = Payment.objects.get(reference=f'ORDER_RETURN:{order_return.id}')
        self.assertEqual(float(refund_payment.amount), 80.0)
        self.assertEqual(Payment.objects.filter(reference=f'ORDER_RETURN:{order_return.id}').count(), 1)
        self.cashbook.refresh_from_db()
        self.assertEqual(float(self.cashbook.balance), 999920.0)

        cancel_response = self.client.post(
            reverse('api_save_order_return'),
            data=json.dumps({
                'id': order_return.id,
                'code': order_return.code,
                'order_id': order.id,
                'return_date': date.today().isoformat(),
                'total_refund': 80,
                'status': 3,
                'payment_method_option_id': self.payment_method.id,
            }),
            content_type='application/json',
        )
        self.assertEqual(cancel_response.json()['status'], 'ok', msg=cancel_response.content.decode())

        refund_payment.refresh_from_db()
        self.assertEqual(refund_payment.status, 2)
        self.cashbook.refresh_from_db()
        self.assertEqual(float(self.cashbook.balance), 1000000.0)

    def test_pos_checkout_clamps_negative_total_to_zero(self):
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=1)

        response = self.client.post(
            reverse('api_pos_checkout'),
            data=json.dumps({
                'items': [{
                    'product_id': self.product.id,
                    'quantity': 1,
                    'unit_price': 100,
                    'total_price': 100,
                    'discount_percent': 0,
                }],
                'total_amount': 100,
                'discount_amount': 150,
                'final_amount': -50,
                'paid_amount': -50,
                'status': 5,
                'payment_status': 2,
                'note': 'POS âm',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        order = Order.objects.get(id=payload['order_id'])
        self.assertEqual(float(order.total_amount), 100.0)
        self.assertEqual(float(order.final_amount), 0.0)
        self.assertEqual(float(order.paid_amount), 0.0)
        self.assertEqual(order.payment_status, 2)
        self.assertEqual(order.receipts.count(), 0)

    def test_print_warranty_uses_custom_selected_items(self):
        order = self._create_order(code='DH-WARRANTY-CUSTOM', status=5)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=10,
            unit_price=100,
            total_price=1000,
        )

        response = self.client.get(
            reverse('api_print_order'),
            {
                'id': order.id,
                'type': 'warranty',
                'source': 'order',
                'warranty_items': json.dumps([{
                    'code': 'MAY-BH',
                    'name': 'Máy cần bảo hành',
                    'unit': 'Cái',
                    'quantity': 1,
                    'serial': 'SN001',
                    'warranty_term': '12 tháng',
                    'note': 'Chỉ bảo hành máy',
                }]),
            },
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Máy cần bảo hành', content)
        self.assertIn('SN001', content)
        self.assertIn('12 tháng', content)
        self.assertNotIn('Sản phẩm test đơn hàng', content)

    def test_print_warranty_empty_custom_items_does_not_fallback_to_all_products(self):
        order = self._create_order(code='DH-WARRANTY-EMPTY', status=5)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=100,
            total_price=100,
        )

        response = self.client.get(
            reverse('api_print_order'),
            {
                'id': order.id,
                'type': 'warranty',
                'source': 'order',
                'warranty_items': json.dumps([]),
            },
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Chưa chọn sản phẩm bảo hành', content)
        self.assertNotIn('Sản phẩm test đơn hàng', content)
