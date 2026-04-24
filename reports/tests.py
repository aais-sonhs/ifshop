from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from customers.models import Customer
from orders.models import Order, OrderItem, OrderReturn
from products.models import Product, Warehouse
from system_management.models import Brand, Store, UserProfile


class SalesReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name='Brand Report')
        cls.store = Store.objects.create(brand=cls.brand, name='Store Report', code='SRP')
        cls.user = User.objects.create_user(username='acct_report', password='pass123')
        UserProfile.objects.create(user=cls.user, store=cls.store, position='Kế toán')

        cls.customer = Customer.objects.create(
            store=cls.store,
            code='KH-RP-001',
            name='Khách báo cáo',
            created_by=cls.user,
        )
        cls.warehouse = Warehouse.objects.create(store=cls.store, code='KHO-RP', name='Kho báo cáo')
        cls.product = Product.objects.create(
            store=cls.store,
            code='SP-RP-001',
            name='Sản phẩm báo cáo',
            created_by=cls.user,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_api_report_sales_counts_linked_returns(self):
        today = date.today()
        order = Order.objects.create(
            code='DH-RP-001',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=100,
            final_amount=100,
            paid_amount=100,
            order_date=today,
            salesperson='Nhân viên A',
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=100,
            cost_price=60,
            total_price=100,
        )
        OrderReturn.objects.create(
            code='TH-RP-001',
            order=order,
            customer=self.customer,
            warehouse=self.warehouse,
            status=2,
            total_refund=25,
            return_date=today,
            created_by=self.user,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['summary']['total_returns'], 25.0)
        self.assertEqual(payload['summary']['returns_count'], 1)
        self.assertEqual(len(payload['return_orders']), 1)
        self.assertEqual(payload['return_orders'][0]['order_code'], order.code)

    def test_api_report_sales_keeps_orphan_return_with_scope_fallback(self):
        today = date.today()
        OrderReturn.objects.create(
            code='TH-RP-ORPHAN',
            customer=self.customer,
            warehouse=self.warehouse,
            status=2,
            total_refund=30,
            return_date=today,
            created_by=self.user,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['summary']['total_returns'], 30.0)
        self.assertEqual(payload['summary']['returns_count'], 1)
        self.assertEqual(len(payload['return_orders']), 1)
        self.assertEqual(payload['return_orders'][0]['order_code'], '(Thiếu đơn gốc)')
        self.assertEqual(payload['return_orders'][0]['store_name'], self.store.name)

    def test_api_report_sales_allocates_order_level_discount_to_item_scope(self):
        today = date.today()
        order = Order.objects.create(
            code='DH-RP-DISCOUNT',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=100,
            discount_amount=20,
            final_amount=80,
            paid_amount=80,
            order_date=today,
            salesperson='Nhân viên A',
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=100,
            cost_price=60,
            total_price=100,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'product_id': self.product.id,
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['summary']['total_revenue'], 80.0)
        self.assertEqual(payload['summary']['total_profit'], 20.0)
        self.assertEqual(payload['order_details'][0]['revenue'], 80.0)
        self.assertEqual(payload['top_products'][0]['amount'], 80.0)
