from datetime import date
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from customers.models import CafeTable, Customer
from orders.models import Order
from system_management.models import Brand, Store, UserProfile


class CustomerScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name='Customers Brand')
        cls.store = Store.objects.create(brand=cls.brand, name='Customers Store A', code='CSA')
        cls.other_store = Store.objects.create(brand=cls.brand, name='Customers Store B', code='CSB')

        cls.user = User.objects.create_user(username='customer_user_a', password='pass123')
        cls.other_user = User.objects.create_user(username='customer_user_b', password='pass123')
        UserProfile.objects.create(user=cls.user, store=cls.store)
        UserProfile.objects.create(user=cls.other_user, store=cls.other_store)

        cls.customer = Customer.objects.create(
            store=cls.store,
            code='CKH001',
            name='Customer A',
            created_by=cls.user,
        )
        cls.other_customer = Customer.objects.create(
            store=cls.other_store,
            code='CKH002',
            name='Customer B',
            created_by=cls.other_user,
        )

        cls.table = CafeTable.objects.create(store=cls.store, number='1')
        cls.other_table = CafeTable.objects.create(store=cls.other_store, number='2')

    def setUp(self):
        self.client.force_login(self.user)

    def test_save_customer_assigns_default_store(self):
        response = self.client.post(
            reverse('api_save_customer'),
            data=json.dumps({
                'code': 'CKH003',
                'name': 'Customer New',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())

        customer = Customer.objects.get(code='CKH003')
        self.assertEqual(customer.store_id, self.store.id)

    def test_save_customer_rejects_foreign_customer_edit(self):
        response = self.client.post(
            reverse('api_save_customer'),
            data=json.dumps({
                'id': self.other_customer.id,
                'code': self.other_customer.code,
                'name': 'Updated Foreign Customer',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['message'], 'Không tìm thấy khách hàng')

    def test_adjust_points_rejects_foreign_customer(self):
        response = self.client.post(
            reverse('api_adjust_points'),
            data=json.dumps({
                'customer_id': self.other_customer.id,
                'points': 10,
                'type': 1,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['message'], 'Không tìm thấy khách hàng')

    def test_update_table_status_rejects_foreign_table(self):
        response = self.client.post(
            reverse('api_update_table_status'),
            data=json.dumps({
                'id': self.other_table.id,
                'status': 1,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['message'], 'Không tìm thấy bàn')

    def test_get_customers_uses_live_order_metrics(self):
        Order.objects.create(
            code='DH-CUST-001',
            store=self.store,
            customer=self.customer,
            status=5,
            payment_status=1,
            total_amount=100,
            final_amount=100,
            paid_amount=40,
            order_date=date.today(),
            created_by=self.user,
        )

        response = self.client.get(reverse('api_get_customers'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = next(item for item in payload['data'] if item['id'] == self.customer.id)
        self.assertEqual(row['total_purchased'], 100.0)
        self.assertEqual(row['total_debt'], 60.0)
