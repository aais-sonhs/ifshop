from datetime import date
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from customers.models import CafeTable, Customer
from orders.models import Order, OrderItem
from products.models import Product
from system_management.models import Brand, Store, UserProfile


class CustomerScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username='customer_manager', password='pass123')
        cls.brand = Brand.objects.create(name='Customers Brand')
        cls.brand.owner = cls.manager
        cls.brand.save(update_fields=['owner'])
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

    def test_save_customer_auto_generates_code_when_blank(self):
        response = self.client.post(
            reverse('api_save_customer'),
            data=json.dumps({
                'name': 'Customer Auto Code',
                'phone': '0909009009',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())

        customer = Customer.objects.get(name='Customer Auto Code')
        self.assertRegex(customer.code, r'^KH\d{3}$')
        self.assertEqual(customer.phone, '0909009009')
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

    def test_regular_staff_cannot_adjust_points(self):
        response = self.client.post(
            reverse('api_adjust_points'),
            data=json.dumps({
                'customer_id': self.customer.id,
                'points': 10,
                'type': 1,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('quyền', payload['message'])

    def test_adjust_points_rejects_non_positive_points(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse('api_adjust_points'),
            data=json.dumps({
                'customer_id': self.customer.id,
                'points': -10,
                'type': 2,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('lớn hơn 0', payload['message'])

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

    def test_update_table_status_rejects_foreign_order(self):
        other_order = Order.objects.create(
            code='DH-TABLE-FOREIGN',
            store=self.other_store,
            customer=self.other_customer,
            total_amount=100,
            final_amount=100,
            order_date=date.today(),
            created_by=self.other_user,
        )

        response = self.client.post(
            reverse('api_update_table_status'),
            data=json.dumps({
                'id': self.table.id,
                'status': 1,
                'order_id': other_order.id,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Đơn hàng', payload['message'])
        self.table.refresh_from_db()
        self.assertIsNone(self.table.current_order_id)

    def test_regular_staff_cannot_save_customer_group(self):
        response = self.client.post(
            reverse('api_save_customer_group'),
            data=json.dumps({
                'name': 'VIP',
                'discount_percent': 10,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['status'], 'error')

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

    def test_customer_unpaid_metrics_ignore_canceled_orders(self):
        active_unpaid = Order.objects.create(
            code='DH-CUST-UNPAID',
            store=self.store,
            customer=self.customer,
            status=1,
            payment_status=0,
            total_amount=100,
            final_amount=100,
            paid_amount=0,
            order_date=date.today(),
            created_by=self.user,
        )
        canceled_unpaid = Order.objects.create(
            code='DH-CUST-CANCELED-UNPAID',
            store=self.store,
            customer=self.customer,
            status=6,
            payment_status=0,
            total_amount=500,
            final_amount=500,
            paid_amount=0,
            order_date=date.today(),
            created_by=self.user,
        )

        customers_response = self.client.get(reverse('api_get_customers'))
        self.assertEqual(customers_response.status_code, 200)
        customer_payload = next(
            item for item in customers_response.json()['data']
            if item['id'] == self.customer.id
        )
        self.assertEqual(customer_payload['total_purchased'], 100.0)
        self.assertEqual(customer_payload['total_debt'], 100.0)
        self.assertEqual(customer_payload['unpaid_order_count'], 1)

        orders_response = self.client.get(reverse('api_customer_orders'), {'customer_id': self.customer.id})
        self.assertEqual(orders_response.status_code, 200)
        orders_payload = orders_response.json()
        self.assertEqual(orders_payload['summary']['total_debt'], 100.0)
        self.assertEqual(orders_payload['summary']['total_cancelled'], 1)
        active_payload = next(item for item in orders_payload['orders'] if item['id'] == active_unpaid.id)
        canceled_payload = next(item for item in orders_payload['orders'] if item['id'] == canceled_unpaid.id)
        self.assertEqual(active_payload['debt'], 100.0)
        self.assertEqual(canceled_payload['debt'], 0)

    def test_customer_order_history_includes_product_price_filters_and_service_lines(self):
        product = Product.objects.create(
            store=self.store,
            code='SP-CUST-HIST',
            name='Máy lịch sử',
            unit='Cái',
            created_by=self.user,
        )
        order = Order.objects.create(
            code='DH-CUST-HIST',
            store=self.store,
            customer=self.customer,
            status=5,
            payment_status=2,
            total_amount=350,
            final_amount=350,
            paid_amount=350,
            order_date=date.today(),
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=2,
            unit_price=100,
            discount_percent=10,
            total_price=180,
        )
        OrderItem.objects.create(
            order=order,
            product=None,
            item_name='Dịch vụ cài đặt',
            unit='Lần',
            is_service_line=True,
            quantity=1,
            unit_price=170,
            total_price=170,
        )

        orders_response = self.client.get(reverse('api_customer_orders'), {'customer_id': self.customer.id})

        self.assertEqual(orders_response.status_code, 200)
        orders_payload = orders_response.json()
        self.assertEqual(orders_payload['status'], 'ok', msg=orders_response.content.decode())
        order_payload = next(item for item in orders_payload['orders'] if item['id'] == order.id)
        service_item = next(item for item in order_payload['items'] if item['is_service_line'])
        product_item = next(item for item in order_payload['items'] if item['product_id'] == product.id)
        self.assertEqual(service_item['product_name'], 'Dịch vụ cài đặt')
        self.assertEqual(service_item['product_code'], 'DV')
        self.assertEqual(product_item['net_unit_price'], 90.0)

        customers_response = self.client.get(reverse('api_get_customers'))
        self.assertEqual(customers_response.status_code, 200)
        customer_payload = next(
            item for item in customers_response.json()['data']
            if item['id'] == self.customer.id
        )
        self.assertIn('Máy lịch sử', customer_payload['purchased_product_search'])
        self.assertIn('Dịch vụ cài đặt', customer_payload['purchased_product_search'])
        self.assertTrue(any(
            item['net_unit_price'] == 90.0
            and item['quantity'] == 2.0
            and item['order_code'] == order.code
            for item in customer_payload['purchase_filter_items']
        ))
