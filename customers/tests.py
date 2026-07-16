from datetime import date
import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from customers.models import CafeTable, Customer, CustomerAddress
from customers.views import add_loyalty_points_for_order
from orders.models import Order, OrderItem
from products.models import Product
from system_management.models import Brand, BusinessConfig, Store, UserProfile


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

    def test_save_customer_persists_customer_kind_and_api_returns_display(self):
        response = self.client.post(
            reverse('api_save_customer'),
            data=json.dumps({
                'code': 'CKH003K',
                'name': 'Customer Wholesale',
                'customer_kind': Customer.CUSTOMER_KIND_WHOLESALE,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())

        customer = Customer.objects.get(code='CKH003K')
        self.assertEqual(customer.customer_kind, Customer.CUSTOMER_KIND_WHOLESALE)

        customers_response = self.client.get(reverse('api_get_customers'))
        self.assertEqual(customers_response.status_code, 200)
        row = next(item for item in customers_response.json()['data'] if item['id'] == customer.id)
        self.assertEqual(row['customer_kind'], Customer.CUSTOMER_KIND_WHOLESALE)
        self.assertEqual(row['customer_kind_display'], 'Khách buôn / sỉ')

    def test_save_customer_persists_multiple_delivery_addresses_and_api_returns_them(self):
        response = self.client.post(
            reverse('api_save_customer'),
            data=json.dumps({
                'id': self.customer.id,
                'code': self.customer.code,
                'name': self.customer.name,
                'address': 'Địa chỉ mặc định',
                'delivery_addresses': [
                    {'label': 'Kho Hà Nội', 'address': 'Số 1 Tràng Tiền, Hà Nội'},
                    {'label': 'Chi nhánh 2', 'address': 'Số 2 Nguyễn Huệ, TP.HCM'},
                ],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())
        self.assertEqual(
            list(CustomerAddress.objects.filter(customer=self.customer).values_list('label', 'address')),
            [
                ('Kho Hà Nội', 'Số 1 Tràng Tiền, Hà Nội'),
                ('Chi nhánh 2', 'Số 2 Nguyễn Huệ, TP.HCM'),
            ],
        )

        customers_response = self.client.get(reverse('api_get_customers'))
        row = next(
            item for item in customers_response.json()['data']
            if item['id'] == self.customer.id
        )
        self.assertEqual(row['address'], 'Địa chỉ mặc định')
        self.assertEqual(
            [(item['label'], item['address']) for item in row['delivery_addresses']],
            [
                ('Kho Hà Nội', 'Số 1 Tràng Tiền, Hà Nội'),
                ('Chi nhánh 2', 'Số 2 Nguyễn Huệ, TP.HCM'),
            ],
        )

    def test_save_customer_replaces_removed_delivery_addresses(self):
        CustomerAddress.objects.create(
            customer=self.customer,
            label='Điểm cũ',
            address='Địa chỉ cũ',
        )

        response = self.client.post(
            reverse('api_save_customer'),
            data=json.dumps({
                'id': self.customer.id,
                'code': self.customer.code,
                'name': self.customer.name,
                'delivery_addresses': [
                    {'label': 'Điểm mới', 'address': 'Địa chỉ mới'},
                ],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())
        self.assertEqual(
            list(CustomerAddress.objects.filter(customer=self.customer).values_list('label', 'address')),
            [('Điểm mới', 'Địa chỉ mới')],
        )

    def test_get_customers_returns_unique_shipping_addresses_from_order_history(self):
        Order.objects.create(
            code='DH-CUST-ADDRESS-OLD',
            store=self.store,
            customer=self.customer,
            status=5,
            shipping_address='12 Nguyễn Trãi, Hà Nội',
            order_date=date(2026, 7, 14),
            created_by=self.user,
        )
        Order.objects.create(
            code='DH-CUST-ADDRESS-LATEST',
            store=self.store,
            customer=self.customer,
            status=5,
            shipping_address='  12 Nguyễn Trãi,   Hà Nội  ',
            order_date=date(2026, 7, 16),
            created_by=self.user,
        )
        Order.objects.create(
            code='DH-CUST-ADDRESS-SECOND',
            store=self.store,
            customer=self.customer,
            status=4,
            shipping_address='Kho công trình Quận 7',
            order_date=date(2026, 7, 15),
            created_by=self.user,
        )
        Order.objects.create(
            code='DH-CUST-ADDRESS-FOREIGN',
            store=self.other_store,
            customer=self.customer,
            status=5,
            shipping_address='Địa chỉ ngoài phạm vi',
            order_date=date(2026, 7, 16),
            created_by=self.other_user,
        )

        response = self.client.get(reverse('api_get_customers'))

        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.json()['data'] if item['id'] == self.customer.id)
        history = row['historical_shipping_addresses']
        self.assertEqual(
            [item['address'] for item in history],
            ['12 Nguyễn Trãi, Hà Nội', 'Kho công trình Quận 7'],
        )
        self.assertEqual(history[0]['last_order_code'], 'DH-CUST-ADDRESS-LATEST')
        self.assertEqual(history[0]['last_order_date'], '16/07/2026')
        self.assertEqual(history[0]['order_count'], 2)

    def test_customer_edit_form_includes_shipping_address_history_section(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse('customer_tbl'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="shipping_address_history_section"')
        self.assertContains(response, 'Địa chỉ giao hàng đã dùng')
        self.assertContains(response, 'function renderHistoricalShippingAddresses(')
        self.assertContains(response, 'customer-code-under-name')
        self.assertNotContains(response, '<th data-col="code">Mã KH</th>', html=True)
        self.assertNotContains(response, "customerColConfig.td('code'")

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

    def test_get_customers_falls_back_to_cached_metrics_without_orders(self):
        self.customer.total_purchased = Decimal('1234000')
        self.customer.total_debt = Decimal('345000')
        self.customer.order_count = 7
        self.customer.imported_legacy_metrics = True
        self.customer.save(update_fields=['total_purchased', 'total_debt', 'order_count', 'imported_legacy_metrics'])

        response = self.client.get(reverse('api_get_customers'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = next(item for item in payload['data'] if item['id'] == self.customer.id)
        self.assertTrue(row['imported_legacy_metrics'])
        self.assertEqual(row['metrics']['source'], 'legacy_import')
        self.assertEqual(row['total_purchased'], 1234000.0)
        self.assertEqual(row['total_debt'], 345000.0)
        self.assertEqual(row['order_count'], 7)

    def test_get_customers_combines_legacy_metrics_with_live_orders(self):
        self.customer.total_purchased = Decimal('1234000')
        self.customer.total_debt = Decimal('345000')
        self.customer.order_count = 7
        self.customer.imported_legacy_metrics = True
        self.customer.save(update_fields=['total_purchased', 'total_debt', 'order_count', 'imported_legacy_metrics'])

        Order.objects.create(
            code='DH-CUST-LEGACY-001',
            store=self.store,
            customer=self.customer,
            status=5,
            payment_status=1,
            total_amount=600000,
            final_amount=600000,
            paid_amount=450000,
            order_date=date.today(),
            created_by=self.user,
        )

        response = self.client.get(reverse('api_get_customers'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = next(item for item in payload['data'] if item['id'] == self.customer.id)
        self.assertTrue(row['imported_legacy_metrics'])
        self.assertEqual(row['metrics']['source'], 'orders_plus_legacy_import')
        self.assertEqual(row['total_purchased'], 1834000.0)
        self.assertEqual(row['total_debt'], 495000.0)
        self.assertEqual(row['order_count'], 8)
        self.assertEqual(row['debt_order_count'], 1)
        self.assertEqual(row['unpaid_order_count'], 0)

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
        self.assertEqual(customer_payload['metrics']['source'], 'orders')
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

    def test_save_customer_persists_extended_import_fields(self):
        response = self.client.post(
            reverse('api_save_customer'),
            data=json.dumps({
                'code': 'CKH004',
                'name': 'Customer Extended',
                'promotion_policy': 'Theo nhóm khách hàng',
                'contact_person': 'Nguyen Van B',
                'contact_phone': '0901002003',
                'contact_email': 'contact@example.com',
                'province': 'Hà Nội',
                'district': 'Ba Đình',
                'ward': 'Trúc Bạch',
                'website': 'example.com',
                'fax': '0241234567',
                'default_price_policy': 'Bảng giá lẻ',
                'default_discount_percent': '7.5',
                'default_payment_method': 'Chuyển khoản',
                'total_purchased': '1500000',
                'total_debt': '250000',
                'imported_legacy_metrics': True,
                'order_count': 3,
                'total_product_quantity': '12.5',
                'total_returned_product_quantity': '1.5',
                'points': 12,
                'membership_level': 2,
                'membership_expiry_date': '31/12/2026',
                'amount_to_next_membership': '500000',
                'last_purchase_at': '25/06/2026 09:03',
                'date_of_birth': '01/01/1990',
                'gender': 1,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())

        customer = Customer.objects.get(code='CKH004')
        self.assertEqual(customer.promotion_policy, 'Theo nhóm khách hàng')
        self.assertEqual(customer.contact_person, 'Nguyen Van B')
        self.assertEqual(customer.contact_phone, '0901002003')
        self.assertEqual(customer.contact_email, 'contact@example.com')
        self.assertEqual(customer.province, 'Hà Nội')
        self.assertEqual(customer.district, 'Ba Đình')
        self.assertEqual(customer.ward, 'Trúc Bạch')
        self.assertEqual(customer.website, 'example.com')
        self.assertEqual(customer.fax, '0241234567')
        self.assertEqual(customer.default_price_policy, 'Bảng giá lẻ')
        self.assertEqual(customer.default_discount_percent, Decimal('7.5'))
        self.assertEqual(customer.default_payment_method, 'Chuyển khoản')
        self.assertTrue(customer.imported_legacy_metrics)
        self.assertEqual(customer.total_purchased, Decimal('1500000'))
        self.assertEqual(customer.total_debt, Decimal('250000'))
        self.assertEqual(customer.order_count, 3)
        self.assertEqual(customer.total_product_quantity, Decimal('12.5'))
        self.assertEqual(customer.total_returned_product_quantity, Decimal('1.5'))
        self.assertEqual(customer.points, 12)
        self.assertEqual(customer.membership_level, 2)
        self.assertEqual(customer.membership_expiry_date.isoformat(), '2026-12-31')
        self.assertEqual(customer.amount_to_next_membership, Decimal('500000'))
        self.assertEqual(customer.last_purchase_at.strftime('%d/%m/%Y %H:%M'), '25/06/2026 09:03')
        self.assertEqual(customer.date_of_birth.isoformat(), '1990-01-01')
        self.assertEqual(customer.gender, 1)

    def test_add_loyalty_points_for_legacy_customer_uses_combined_total_for_membership(self):
        BusinessConfig.objects.update_or_create(
            pk=1,
            defaults={
                'business_type': 'custom',
                'business_name': 'Doanh nghiệp',
                'opt_loyalty_points': True,
                'opt_loyalty_rate': 10000,
            },
        )
        self.customer.total_purchased = Decimal('4900000')
        self.customer.total_debt = Decimal('50000')
        self.customer.order_count = 2
        self.customer.imported_legacy_metrics = True
        self.customer.save(update_fields=['total_purchased', 'total_debt', 'order_count', 'imported_legacy_metrics'])

        order = Order.objects.create(
            code='DH-CUST-LOYALTY-LEGACY',
            store=self.store,
            customer=self.customer,
            status=5,
            payment_status=2,
            total_amount=200000,
            final_amount=200000,
            paid_amount=200000,
            order_date=date.today(),
            created_by=self.user,
        )

        add_loyalty_points_for_order(order)
        self.customer.refresh_from_db()

        self.assertEqual(self.customer.points, 20)
        self.assertEqual(self.customer.total_purchased, Decimal('4900000'))
        self.assertEqual(self.customer.membership_level, 1)

        response = self.client.get(reverse('api_get_customers'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = next(item for item in payload['data'] if item['id'] == self.customer.id)
        self.assertEqual(row['metrics']['source'], 'orders_plus_legacy_import')
        self.assertEqual(row['total_purchased'], 5100000.0)
        self.assertEqual(row['order_count'], 3)
