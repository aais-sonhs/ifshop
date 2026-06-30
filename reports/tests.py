from datetime import date
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from customers.models import Customer, CustomerGroup
from orders.models import Order, OrderItem, OrderReturn
from products.models import Product, ProductCategory, ProductVariant, Warehouse
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

    def test_api_report_sales_rejects_regular_staff(self):
        staff = User.objects.create_user(username='regular_report_staff', password='pass123')
        UserProfile.objects.create(user=staff, store=self.store, position='Quản lý cửa hàng')
        self.client.force_login(staff)

        response = self.client.get(reverse('api_report_sales'))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['status'], 'error')

    def test_api_report_sales_allows_brand_owner(self):
        owner = User.objects.create_user(username='owner_sales_report', password='pass123')
        Brand.objects.create(name='Owner Sales Report Role', owner=owner)
        self.client.force_login(owner)

        response = self.client.get(reverse('api_report_sales'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_api_report_sales_allows_director_position(self):
        director = User.objects.create_user(username='director_report', password='pass123')
        UserProfile.objects.create(user=director, store=self.store, position='Giám đốc')
        self.client.force_login(director)

        response = self.client.get(reverse('api_report_sales'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

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

    def test_api_report_sales_includes_sapo_style_sku_details(self):
        today = date.today()
        variant = ProductVariant.objects.create(
            product=self.product,
            size_name='Size A',
            sku='SKU-RP-001-A',
        )
        seller = User.objects.create_user(
            username='sku_report_seller',
            password='pass123',
            first_name='Minh',
            last_name='Ban Hang',
        )
        order = Order.objects.create(
            code='DH-RP-SKU',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=200,
            discount_amount=20,
            final_amount=180,
            paid_amount=180,
            order_date=today,
            salesperson='Nhân viên SKU',
            created_by=seller,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            variant=variant,
            quantity=2,
            unit_price=100,
            cost_price=70,
            total_price=200,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(len(payload['sku_details']), 1)
        row = payload['sku_details'][0]
        self.assertEqual(row['date'], today.strftime('%d/%m/%Y'))
        self.assertEqual(row['customer'], self.customer.name)
        self.assertEqual(row['product_name'], self.product.name)
        self.assertEqual(row['sku'], 'SKU-RP-001-A')
        self.assertEqual(row['order_code'], order.code)
        self.assertEqual(row['salesperson'], 'Nhân viên SKU')
        self.assertEqual(row['revenue'], 180.0)
        self.assertEqual(row['cost'], 140.0)
        self.assertEqual(row['profit'], 40.0)

    def test_api_report_sales_includes_daily_finance_summary(self):
        today = date.today()
        order = Order.objects.create(
            code='DH-RP-DAILY',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=200,
            discount_amount=20,
            final_amount=180,
            paid_amount=180,
            order_date=today,
            salesperson='Nhân viên ngày',
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=100,
            cost_price=70,
            total_price=200,
        )
        OrderReturn.objects.create(
            code='TH-RP-DAILY',
            order=order,
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
        self.assertEqual(payload['summary']['total_goods_amount'], 200.0)
        self.assertEqual(payload['summary']['total_net_revenue'], 150.0)
        self.assertEqual(payload['summary']['total_gross_profit'], 10.0)
        self.assertEqual(payload['summary']['gross_margin'], 6.7)
        self.assertEqual(len(payload['daily_finance']), 1)
        row = payload['daily_finance'][0]
        self.assertEqual(row['date'], today.strftime('%d/%m/%Y'))
        self.assertEqual(row['goods_amount'], 200.0)
        self.assertEqual(row['revenue'], 180.0)
        self.assertEqual(row['returns'], 30.0)
        self.assertEqual(row['net_revenue'], 150.0)
        self.assertEqual(row['cost'], 140.0)
        self.assertEqual(row['gross_profit'], 10.0)
        self.assertEqual(row['gross_margin'], 6.7)
        self.assertEqual(row['net_profit'], 10.0)

    def test_api_report_sales_filter_options_include_store_users_without_orders(self):
        today = date.today()
        seller = User.objects.create_user(
            username='seller_report',
            password='pass123',
            first_name='Lan',
            last_name='Nguyen',
        )
        UserProfile.objects.create(user=seller, store=self.store)

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertIn('Lan Nguyen', payload['filter_options']['salespersons'])

    def test_api_report_sales_filters_customer_kind_wholesale(self):
        today = date.today()
        wholesale_group = CustomerGroup.objects.create(name='Khách sỉ')
        retail_group = CustomerGroup.objects.create(name='Khách lẻ')
        wholesale_customer = Customer.objects.create(
            store=self.store,
            code='KH-RP-SI',
            name='Khách mua sỉ',
            group=wholesale_group,
            created_by=self.user,
        )
        retail_customer = Customer.objects.create(
            store=self.store,
            code='KH-RP-LE',
            name='Khách mua lẻ',
            group=retail_group,
            created_by=self.user,
        )

        wholesale_order = Order.objects.create(
            code='DH-RP-SI',
            store=self.store,
            customer=wholesale_customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=100,
            final_amount=100,
            paid_amount=100,
            order_date=today,
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=wholesale_order,
            product=self.product,
            quantity=1,
            unit_price=100,
            cost_price=60,
            total_price=100,
        )
        retail_order = Order.objects.create(
            code='DH-RP-LE',
            store=self.store,
            customer=retail_customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=80,
            final_amount=80,
            paid_amount=80,
            order_date=today,
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=retail_order,
            product=self.product,
            quantity=1,
            unit_price=80,
            cost_price=50,
            total_price=80,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'customer_kind': 'wholesale',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['summary']['total_orders'], 1)
        self.assertEqual(payload['order_details'][0]['code'], wholesale_order.code)
        self.assertEqual(payload['order_details'][0]['customer_kind'], 'wholesale')
        self.assertEqual(payload['customer_kind_breakdown'][0]['name'], 'Khách buôn / sỉ')

    def test_api_report_sales_prefers_explicit_customer_kind_field(self):
        today = date.today()
        neutral_group = CustomerGroup.objects.create(name='VIP thân thiết')
        wholesale_customer = Customer.objects.create(
            store=self.store,
            code='KH-RP-EX-SI',
            name='Khách field sỉ',
            group=neutral_group,
            customer_kind=Customer.CUSTOMER_KIND_WHOLESALE,
            created_by=self.user,
        )
        retail_customer = Customer.objects.create(
            store=self.store,
            code='KH-RP-EX-LE',
            name='Khách field lẻ',
            group=neutral_group,
            customer_kind=Customer.CUSTOMER_KIND_RETAIL,
            created_by=self.user,
        )

        wholesale_order = Order.objects.create(
            code='DH-RP-EX-SI',
            store=self.store,
            customer=wholesale_customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=120,
            final_amount=120,
            paid_amount=120,
            order_date=today,
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=wholesale_order,
            product=self.product,
            quantity=1,
            unit_price=120,
            cost_price=70,
            total_price=120,
        )
        retail_order = Order.objects.create(
            code='DH-RP-EX-LE',
            store=self.store,
            customer=retail_customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=80,
            final_amount=80,
            paid_amount=80,
            order_date=today,
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=retail_order,
            product=self.product,
            quantity=1,
            unit_price=80,
            cost_price=40,
            total_price=80,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'customer_kind': 'wholesale',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['summary']['total_orders'], 1)
        self.assertEqual(payload['order_details'][0]['code'], wholesale_order.code)
        self.assertEqual(payload['order_details'][0]['customer_kind'], 'wholesale')
        self.assertEqual(payload['filter_options']['customers'][0]['name'], wholesale_customer.name)

    def test_api_report_sales_root_category_filter_includes_child_type(self):
        today = date.today()
        root_category = ProductCategory.objects.create(name='Máy móc')
        product_type = ProductCategory.objects.create(name='Máy xay', parent=root_category)
        product = Product.objects.create(
            store=self.store,
            code='SP-RP-MAY-XAY',
            name='Máy xay sinh tố',
            category=product_type,
            created_by=self.user,
        )
        order = Order.objects.create(
            code='DH-RP-ROOT-CAT',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=200,
            final_amount=200,
            paid_amount=200,
            order_date=today,
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=1,
            unit_price=200,
            cost_price=120,
            total_price=200,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'category_id': root_category.id,
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['summary']['total_orders'], 1)
        self.assertEqual(payload['product_breakdown'][0]['category'], root_category.name)
        self.assertEqual(payload['product_breakdown'][0]['product_type'], product_type.name)
        self.assertEqual(payload['category_breakdown'][0]['name'], root_category.name)

    def test_api_report_sales_product_type_filter_limits_child_category(self):
        today = date.today()
        root_category = ProductCategory.objects.create(name='Nhóm máy')
        selected_type = ProductCategory.objects.create(name='Máy ép', parent=root_category)
        other_type = ProductCategory.objects.create(name='Máy xay', parent=root_category)
        selected_product = Product.objects.create(
            store=self.store,
            code='SP-RP-MAY-EP',
            name='Máy ép',
            category=selected_type,
            created_by=self.user,
        )
        other_product = Product.objects.create(
            store=self.store,
            code='SP-RP-MAY-XAY-2',
            name='Máy xay khác',
            category=other_type,
            created_by=self.user,
        )
        selected_order = Order.objects.create(
            code='DH-RP-TYPE-1',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=300,
            final_amount=300,
            paid_amount=300,
            order_date=today,
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=selected_order,
            product=selected_product,
            quantity=1,
            unit_price=300,
            cost_price=200,
            total_price=300,
        )
        other_order = Order.objects.create(
            code='DH-RP-TYPE-2',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=150,
            final_amount=150,
            paid_amount=150,
            order_date=today,
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=other_order,
            product=other_product,
            quantity=1,
            unit_price=150,
            cost_price=90,
            total_price=150,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'product_type_id': selected_type.id,
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['summary']['total_orders'], 1)
        self.assertEqual(payload['order_details'][0]['code'], selected_order.code)
        self.assertEqual(payload['product_breakdown'][0]['product_type'], selected_type.name)

    def test_api_report_sales_filters_line_profit_and_shows_loss_order(self):
        today = date.today()
        loss_order = Order.objects.create(
            code='DH-RP-LOSS-LINE',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=100,
            final_amount=100,
            paid_amount=100,
            order_date=today,
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=loss_order,
            product=self.product,
            quantity=1,
            unit_price=100,
            cost_price=130,
            total_price=100,
        )
        profit_order = Order.objects.create(
            code='DH-RP-PROFIT-LINE',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=120,
            final_amount=120,
            paid_amount=120,
            order_date=today,
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=profit_order,
            product=self.product,
            quantity=1,
            unit_price=120,
            cost_price=80,
            total_price=120,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'line_profit_max': -1,
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['summary']['total_orders'], 1)
        self.assertEqual(payload['order_details'][0]['code'], loss_order.code)
        self.assertTrue(payload['order_details'][0]['is_loss'])
        self.assertEqual(payload['summary']['loss_count'], 1)

    def test_export_sales_excel_respects_filters_and_uses_readable_labels(self):
        today = date.today()
        wholesale_group = CustomerGroup.objects.create(name='Khách sỉ')
        retail_group = CustomerGroup.objects.create(name='Khách lẻ')
        wholesale_customer = Customer.objects.create(
            store=self.store,
            code='KH-EX-SI',
            name='Khách mua sỉ Excel',
            group=wholesale_group,
            created_by=self.user,
        )
        retail_customer = Customer.objects.create(
            store=self.store,
            code='KH-EX-LE',
            name='Khách mua lẻ Excel',
            group=retail_group,
            created_by=self.user,
        )
        beverage_root = ProductCategory.objects.create(name='Đồ uống')
        coffee_type = ProductCategory.objects.create(name='Cà phê', parent=beverage_root)
        other_root = ProductCategory.objects.create(name='Thiết bị')
        exported_product = Product.objects.create(
            store=self.store,
            code='SP-EX-COFFEE',
            name='Cà phê hạt',
            category=coffee_type,
            created_by=self.user,
        )
        excluded_product = Product.objects.create(
            store=self.store,
            code='SP-EX-DEVICE',
            name='Máy xay',
            category=other_root,
            created_by=self.user,
        )

        loss_order = Order.objects.create(
            code='DH-EX-LOSS',
            store=self.store,
            customer=wholesale_customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=100,
            final_amount=100,
            paid_amount=100,
            order_date=today,
            salesperson='Nhân viên Excel',
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=loss_order,
            product=exported_product,
            quantity=1,
            unit_price=100,
            cost_price=130,
            total_price=100,
        )

        profit_order = Order.objects.create(
            code='DH-EX-PROFIT',
            store=self.store,
            customer=retail_customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=200,
            final_amount=200,
            paid_amount=200,
            order_date=today,
            salesperson='Nhân viên khác',
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=profit_order,
            product=excluded_product,
            quantity=1,
            unit_price=200,
            cost_price=120,
            total_price=200,
        )

        response = self.client.get(reverse('export_sales_excel'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'customer_kind': 'wholesale',
            'category_id': beverage_root.id,
            'profit_filter': 'loss',
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            response['Content-Type'],
        )

        workbook = load_workbook(BytesIO(response.content))
        self.assertIn('Chi tiết đơn hàng', workbook.sheetnames)
        self.assertEqual(
            workbook.active['A3'].value,
            'Bộ lọc: Xem theo: Ngày | Kiểu khách: Khách buôn / sỉ | Nhóm mặt hàng: Đồ uống | Lợi nhuận: Báo lỗ',
        )

        order_sheet = workbook['Chi tiết đơn hàng']
        exported_order_codes = [
            row[1]
            for row in order_sheet.iter_rows(min_row=2, max_col=2, values_only=True)
            if row[1] and row[1] != 'TỔNG'
        ]
        self.assertEqual(exported_order_codes, [loss_order.code])

        product_sheet = workbook['Mặt hàng']
        exported_product_names = [
            row[1]
            for row in product_sheet.iter_rows(min_row=2, max_col=2, values_only=True)
            if row[1]
        ]
        self.assertEqual(exported_product_names, [exported_product.name])

    def test_api_report_staff_sales_filter_options_include_store_users_without_orders(self):
        today = date.today()
        seller = User.objects.create_user(
            username='staff_sales_report',
            password='pass123',
            first_name='Minh',
            last_name='Tran',
        )
        UserProfile.objects.create(user=seller, store=self.store)

        response = self.client.get(reverse('api_report_staff_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertIn('Minh Tran', payload['salespersons'])
