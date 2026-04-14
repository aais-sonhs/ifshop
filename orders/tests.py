import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from customers.models import Customer
from finance.models import Receipt
from orders.models import Order, Quotation
from products.models import Warehouse
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

    def test_save_order_blocks_edit_when_receipt_exists(self):
        order = self._create_order(code='DH-PAID-001')
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
            data=json.dumps({'id': order.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('đã có phiếu thu', payload['message'])

        order.refresh_from_db()
        self.assertEqual(order.status, 1)
        self.assertEqual(order.final_amount, 100)

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
