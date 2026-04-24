import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from customers.models import Customer
from finance.models import Receipt
from orders.models import Order, OrderItem, OrderReturn, Quotation
from products.models import Product, Warehouse
from system_management.models import Brand, Store, UserProfile


class OrderRiskFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name='Test Brand')
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

        order.refresh_from_db()
        self.assertEqual(order.status, 1)
        self.assertEqual(order.final_amount, 100)

    def test_save_order_blocks_financial_edit_when_receipt_exists(self):
        order = self._create_order(code='DH-PAID-EDIT-001', status=0)
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
                'status': 1,
                'discount_amount': 10,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('chiết khấu', payload['message'])

        order.refresh_from_db()
        self.assertEqual(order.status, 0)
        self.assertEqual(order.discount_amount, 0)

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
        self.assertEqual(payload['message'], 'Lưu thành công')

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

    def test_pos_checkout_clamps_negative_total_to_zero(self):
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
