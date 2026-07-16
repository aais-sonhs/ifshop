from datetime import date
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from customers.models import Customer, CustomerGroup
from orders.models import Order, OrderItem, OrderReturn, OrderReturnItem
from products.models import (
    GoodsReceipt,
    Product,
    ProductCategory,
    ProductStock,
    ProductVariant,
    Supplier,
    Warehouse,
)
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

    def test_purchase_report_groups_completed_receipts_by_supplier_and_filters_supplier(self):
        today = date.today()
        supplier_a = Supplier.objects.create(code='NCC-RP-A', name='NCC báo cáo A')
        supplier_b = Supplier.objects.create(code='NCC-RP-B', name='NCC báo cáo B')
        for code, supplier, amount, status in [
            ('PN-RP-A1', supplier_a, 100, 1),
            ('PN-RP-A2', supplier_a, 200, 1),
            ('PN-RP-A-DRAFT', supplier_a, 900, 0),
            ('PN-RP-B1', supplier_b, 400, 1),
        ]:
            GoodsReceipt.objects.create(
                code=code,
                supplier=supplier,
                warehouse=self.warehouse,
                receipt_date=today,
                total_amount=amount,
                status=status,
                created_by=self.user,
            )

        response = self.client.get(reverse('api_report_purchases'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        summary_by_supplier = {row['supplier']: row for row in payload['supplier_summary']}
        self.assertEqual(payload['summary']['total_amount'], 700.0)
        self.assertEqual(payload['summary']['total_count'], 3)
        self.assertEqual(payload['summary']['total_suppliers'], 2)
        self.assertEqual(summary_by_supplier[supplier_a.name]['receipt_count'], 2)
        self.assertEqual(summary_by_supplier[supplier_a.name]['total_amount'], 300.0)
        self.assertEqual(summary_by_supplier[supplier_b.name]['total_amount'], 400.0)

        filtered = self.client.get(reverse('api_report_purchases'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'supplier_id': supplier_a.id,
        }).json()
        self.assertEqual(filtered['summary']['total_amount'], 300.0)
        self.assertEqual(filtered['summary']['total_count'], 2)
        self.assertEqual(len(filtered['supplier_summary']), 1)
        self.assertTrue(all(row['supplier'] == supplier_a.name for row in filtered['data']))

    def test_export_purchase_report_includes_supplier_summary_sheet(self):
        today = date.today()
        supplier = Supplier.objects.create(code='NCC-RP-EX', name='NCC xuất báo cáo')
        GoodsReceipt.objects.create(
            code='PN-RP-EX',
            supplier=supplier,
            warehouse=self.warehouse,
            receipt_date=today,
            total_amount=750,
            status=1,
            created_by=self.user,
        )

        response = self.client.get(reverse('export_purchases_excel'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'supplier_id': supplier.id,
        })

        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content), data_only=True)
        self.assertIn('Tổng hợp NCC', workbook.sheetnames)
        summary_sheet = workbook['Tổng hợp NCC']
        self.assertEqual(summary_sheet['B5'].value, supplier.name)
        self.assertEqual(summary_sheet['C5'].value, 1)
        self.assertEqual(summary_sheet['D5'].value, 750)

    def test_inventory_report_alert_card_controls_are_available(self):
        owner = User.objects.create_user(username='owner_inventory_report', password='pass123')
        self.brand.owner = owner
        self.brand.save(update_fields=['owner'])
        self.client.force_login(owner)

        response = self.client.get(reverse('report_inventory'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="alert_box"')
        self.assertContains(response, '<option value="all">Tất cả cảnh báo</option>', html=True)
        self.assertContains(response, 'Cần nhập tối thiểu')
        self.assertContains(response, 'id="inventory_alert_filter_notice"')
        self.assertContains(response, 'activateInventoryAlertCard')

    def test_api_inventory_report_identifies_low_stock_and_restock_quantity(self):
        low_product = Product.objects.create(
            store=self.store,
            code='SP-RP-LOW',
            name='Sản phẩm thiếu tồn',
            min_stock=10,
            max_stock=30,
            created_by=self.user,
        )
        negative_product = Product.objects.create(
            store=self.store,
            code='SP-RP-NEGATIVE',
            name='Sản phẩm tồn âm',
            min_stock=0,
            created_by=self.user,
        )
        high_product = Product.objects.create(
            store=self.store,
            code='SP-RP-HIGH',
            name='Sản phẩm vượt tồn',
            min_stock=2,
            max_stock=20,
            created_by=self.user,
        )
        ProductStock.objects.create(product=low_product, warehouse=self.warehouse, quantity=4)
        ProductStock.objects.create(product=negative_product, warehouse=self.warehouse, quantity=-2)
        ProductStock.objects.create(product=high_product, warehouse=self.warehouse, quantity=25)

        response = self.client.get(reverse('api_report_inventory'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = {row['product_code']: row for row in payload['data']}
        self.assertEqual(rows[low_product.code]['alert_type'], 'danger')
        self.assertEqual(rows[low_product.code]['restock_needed'], 6.0)
        self.assertEqual(rows[negative_product.code]['alert_type'], 'danger')
        self.assertEqual(rows[negative_product.code]['restock_needed'], 2.0)
        self.assertEqual(rows[high_product.code]['alert_type'], 'warning')
        self.assertEqual(rows[high_product.code]['restock_needed'], 0)
        self.assertEqual(payload['summary']['alert_count'], 3)
        self.assertEqual(payload['summary']['low_stock_count'], 2)
        self.assertEqual(payload['summary']['high_stock_count'], 1)

    def test_inventory_value_sums_positive_stock_times_cost_without_negative_offset(self):
        positive_product = Product.objects.create(
            store=self.store,
            code='SP-RP-VALUE-POS',
            name='Sản phẩm còn tồn',
            cost_price=120000,
            created_by=self.user,
        )
        negative_product = Product.objects.create(
            store=self.store,
            code='SP-RP-VALUE-NEG',
            name='Sản phẩm âm kho',
            cost_price=50000,
            created_by=self.user,
        )
        deleted_product = Product.objects.create(
            store=self.store,
            code='SP-RP-VALUE-DELETED',
            name='Sản phẩm đã xóa',
            cost_price=999999,
            created_by=self.user,
        )
        ProductStock.objects.create(product=positive_product, warehouse=self.warehouse, quantity=3)
        ProductStock.objects.create(product=negative_product, warehouse=self.warehouse, quantity=-2)
        ProductStock.objects.create(product=deleted_product, warehouse=self.warehouse, quantity=10)
        deleted_product.delete()

        payload = self.client.get(reverse('api_report_inventory')).json()
        rows = {row['product_code']: row for row in payload['data']}

        self.assertEqual(rows[positive_product.code]['stock_value'], 360000.0)
        self.assertEqual(rows[negative_product.code]['stock_value'], 0.0)
        self.assertNotIn(deleted_product.code, rows)
        self.assertEqual(payload['summary']['total_value'], 360000.0)

    def test_api_report_sales_defaults_to_realized_orders(self):
        today = date.today()
        created_orders = []
        for status, suffix in ((3, 'PACK'), (4, 'EXPORTED'), (5, 'DONE'), (6, 'CANCELLED')):
            order = Order.objects.create(
                code=f'DH-RP-SCOPE-{suffix}',
                store=self.store,
                customer=self.customer,
                warehouse=self.warehouse,
                status=status,
                total_amount=100,
                final_amount=100,
                order_date=today,
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
            created_orders.append(order)

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['summary']['total_orders'], 2)
        self.assertEqual(
            {row['code'] for row in payload['order_details']},
            {created_orders[1].code, created_orders[2].code},
        )
        self.assertEqual(payload['filters_applied']['order_scope'], 'realized')

    def test_api_report_sales_all_active_scope_includes_non_cancelled_orders(self):
        today = date.today()
        expected_codes = set()
        for status, suffix in ((1, 'ORDER'), (3, 'PACK'), (4, 'EXPORTED'), (5, 'DONE'), (6, 'CANCELLED')):
            order = Order.objects.create(
                code=f'DH-RP-ALL-{suffix}',
                store=self.store,
                customer=self.customer,
                warehouse=self.warehouse,
                status=status,
                total_amount=100,
                final_amount=100,
                order_date=today,
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
            if status != 6:
                expected_codes.add(order.code)

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'order_scope': 'all_active',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['summary']['total_orders'], 4)
        self.assertEqual({row['code'] for row in payload['order_details']}, expected_codes)
        self.assertEqual(payload['filters_applied']['order_scope'], 'all_active')

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

    def test_api_report_sales_includes_order_other_fee_in_revenue_and_profit(self):
        today = date.today()
        order = Order.objects.create(
            code='DH-RP-OTHER-FEE',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=100,
            discount_amount=10,
            shipping_fee=5,
            other_fee=20,
            final_amount=115,
            paid_amount=115,
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
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = next(item for item in payload['order_details'] if item['id'] == order.id)
        self.assertEqual(row['goods_amount'], 100.0)
        self.assertEqual(row['discount_amount'], 10.0)
        self.assertEqual(row['shipping_fee'], 5.0)
        self.assertEqual(row['other_fee'], 20.0)
        self.assertEqual(row['revenue'], 115.0)
        self.assertEqual(row['profit'], 55.0)

    def test_api_report_sales_falls_back_when_legacy_order_item_cost_is_zero(self):
        today = date.today()
        self.product.cost_price = 60
        self.product.import_price = 65
        self.product.save(update_fields=['cost_price', 'import_price'])
        order = Order.objects.create(
            code='DH-RP-LEGACY-ZERO-COST',
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
            cost_price=0,
            total_price=100,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = next(item for item in payload['order_details'] if item['id'] == order.id)
        self.assertEqual(row['cost'], 60.0)
        self.assertEqual(row['profit'], 40.0)

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
        order_return = OrderReturn.objects.create(
            code='TH-RP-DAILY',
            order=order,
            customer=self.customer,
            warehouse=self.warehouse,
            status=2,
            total_refund=30,
            return_date=today,
            created_by=self.user,
        )
        OrderReturnItem.objects.create(
            order_return=order_return,
            product=self.product,
            quantity=1,
            unit_price=30,
            total_price=30,
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
        self.assertEqual(payload['summary']['total_sales_cost'], 140.0)
        self.assertEqual(payload['summary']['total_return_cost'], 70.0)
        self.assertEqual(payload['summary']['total_net_cost'], 70.0)
        self.assertEqual(payload['summary']['total_gross_profit'], 80.0)
        self.assertEqual(payload['summary']['gross_margin'], 53.3)
        self.assertEqual(len(payload['daily_finance']), 1)
        row = payload['daily_finance'][0]
        self.assertEqual(row['date'], today.strftime('%d/%m/%Y'))
        self.assertEqual(row['goods_amount'], 200.0)
        self.assertEqual(row['revenue'], 180.0)
        self.assertEqual(row['returns'], 30.0)
        self.assertEqual(row['net_revenue'], 150.0)
        self.assertEqual(row['gross_cost'], 140.0)
        self.assertEqual(row['return_cost'], 70.0)
        self.assertEqual(row['cost'], 70.0)
        self.assertEqual(row['gross_profit'], 80.0)
        self.assertEqual(row['gross_margin'], 53.3)
        self.assertEqual(row['net_profit'], 80.0)

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
        self.assertEqual(payload['order_details'][0]['loss_product_names'], self.product.name)
        self.assertEqual(len(payload['order_details'][0]['loss_products']), 1)
        loss_product = payload['order_details'][0]['loss_products'][0]
        self.assertEqual(loss_product['product_name'], self.product.name)
        self.assertEqual(loss_product['unit_revenue'], 100.0)
        self.assertEqual(loss_product['unit_cost'], 130.0)
        self.assertEqual(loss_product['loss_amount'], 30.0)
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
            'Bộ lọc: Xem theo: Ngày | Phạm vi đơn: Đã xuất kho + Hoàn thành | Kiểu khách: Khách buôn / sỉ | Nhóm mặt hàng: Đồ uống | Lợi nhuận: Báo lỗ',
        )

        order_sheet = workbook['Chi tiết đơn hàng']
        exported_order_codes = [
            row[1]
            for row in order_sheet.iter_rows(min_row=2, max_col=2, values_only=True)
            if row[1] and row[1] != 'TỔNG'
        ]
        self.assertEqual(exported_order_codes, [loss_order.code])
        order_headers = [cell.value for cell in order_sheet[1]]
        loss_product_col = order_headers.index('Sản phẩm lỗ') + 1
        self.assertEqual(order_sheet.cell(row=2, column=loss_product_col).value, exported_product.name)

        product_sheet = workbook['Mặt hàng']
        exported_product_names = [
            row[1]
            for row in product_sheet.iter_rows(min_row=2, max_col=2, values_only=True)
            if row[1]
        ]
        self.assertEqual(exported_product_names, [exported_product.name])

    def test_export_sales_excel_respects_order_scope(self):
        today = date.today()
        pending_order = Order.objects.create(
            code='DH-EX-SCOPE-PENDING',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=1,
            total_amount=100,
            final_amount=100,
            order_date=today,
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=pending_order,
            product=self.product,
            quantity=1,
            unit_price=100,
            cost_price=60,
            total_price=100,
        )

        default_response = self.client.get(reverse('export_sales_excel'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })
        default_workbook = load_workbook(BytesIO(default_response.content))
        default_codes = [
            row[1]
            for row in default_workbook['Chi tiết đơn hàng'].iter_rows(min_row=2, max_col=2, values_only=True)
            if row[1] and row[1] != 'TỔNG'
        ]
        self.assertNotIn(pending_order.code, default_codes)

        all_active_response = self.client.get(reverse('export_sales_excel'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'order_scope': 'all_active',
        })
        all_active_workbook = load_workbook(BytesIO(all_active_response.content))
        all_active_codes = [
            row[1]
            for row in all_active_workbook['Chi tiết đơn hàng'].iter_rows(min_row=2, max_col=2, values_only=True)
            if row[1] and row[1] != 'TỔNG'
        ]
        self.assertIn(pending_order.code, all_active_codes)

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
