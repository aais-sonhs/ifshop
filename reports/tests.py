from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from customers.models import Customer, CustomerGroup
from finance.models import Payment, Receipt
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

    def test_finance_report_adds_completed_payments_and_goods_receipts_in_scope(self):
        self.brand.owner = self.user
        self.brand.save(update_fields=['owner'])
        second_store = Store.objects.create(
            brand=self.brand,
            name='Store Report 2',
            code='SRP2',
        )
        second_warehouse = Warehouse.objects.create(
            store=second_store,
            name='Kho báo cáo 2',
            code='KHO-RP-2',
        )
        foreign_brand = Brand.objects.create(name='Foreign Report Brand')
        foreign_store = Store.objects.create(
            brand=foreign_brand,
            name='Foreign Report Store',
            code='FRS',
        )
        foreign_warehouse = Warehouse.objects.create(
            store=foreign_store,
            name='Kho báo cáo ngoài phạm vi',
            code='KHO-RP-FOREIGN',
        )
        to_day = date.today()
        from_day = to_day - timedelta(days=1)
        outside_day = from_day - timedelta(days=1)

        goods_receipt_specs = [
            ('PN-RP-DONE-FROM', self.warehouse, from_day, 4000, 1),
            ('PN-RP-DONE-TO', self.warehouse, to_day, 6000, 1),
            ('PN-RP-SECOND-STORE', second_warehouse, to_day, 20000, 1),
            ('PN-RP-DRAFT', self.warehouse, to_day, 30000, 0),
            ('PN-RP-CANCELED', self.warehouse, to_day, 40000, 2),
            ('PN-RP-OUTSIDE-DATE', self.warehouse, outside_day, 50000, 1),
            ('PN-RP-FOREIGN-STORE', foreign_warehouse, to_day, 60000, 1),
        ]
        for code, warehouse, receipt_date, amount, status in goods_receipt_specs:
            GoodsReceipt.objects.create(
                code=code,
                warehouse=warehouse,
                receipt_date=receipt_date,
                total_amount=amount,
                status=status,
                created_by=self.user,
            )

        receipt_specs = [
            ('PT-RP-DONE-FROM', self.store, from_day, 100, 1),
            ('PT-RP-DONE-TO', self.store, to_day, 250, 1),
            ('PT-RP-SECOND-STORE', second_store, to_day, 600, 1),
            ('PT-RP-DRAFT', self.store, to_day, 900, 0),
            ('PT-RP-CANCELED', self.store, to_day, 800, 2),
            ('PT-RP-OUTSIDE-DATE', self.store, outside_day, 700, 1),
            ('PT-RP-FOREIGN-STORE', foreign_store, to_day, 5000, 1),
        ]
        for code, store, receipt_date, amount, status in receipt_specs:
            Receipt.objects.create(
                code=code,
                store=store,
                amount=amount,
                receipt_date=receipt_date,
                status=status,
                created_by=self.user,
            )

        payment_specs = [
            ('PC-RP-DONE-FROM', self.store, from_day, 40, 1),
            ('PC-RP-DONE-TO', self.store, to_day, 60, 1),
            ('PC-RP-SECOND-STORE', second_store, to_day, 90, 1),
            ('PC-RP-DRAFT', self.store, to_day, 300, 0),
            ('PC-RP-CANCELED', self.store, to_day, 200, 2),
            ('PC-RP-OUTSIDE-DATE', self.store, outside_day, 100, 1),
            ('PC-RP-FOREIGN-STORE', foreign_store, to_day, 500, 1),
        ]
        for code, store, payment_date, amount, status in payment_specs:
            Payment.objects.create(
                code=code,
                store=store,
                amount=amount,
                payment_date=payment_date,
                status=status,
                created_by=self.user,
            )

        response = self.client.get(reverse('api_report_finance'), {
            'from_date': from_day.isoformat(),
            'to_date': to_day.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['summary']['total_income'], 950.0)
        self.assertEqual(payload['summary']['payment_expense'], 190.0)
        self.assertEqual(payload['summary']['goods_receipt_expense'], 30000.0)
        self.assertEqual(payload['summary']['total_expense'], 30190.0)
        self.assertEqual(payload['summary']['net_profit'], -29240.0)
        category_rows = {row['name']: row for row in payload['categories']}
        self.assertEqual(category_rows['Hàng nhập (phiếu nhập)']['expense'], 30000.0)
        self.assertEqual(sum(row['expense'] for row in payload['categories']), 30190.0)

        store_rows = {row['store_id']: row for row in payload['store_breakdown']}
        self.assertEqual(store_rows[self.store.id]['income'], 350.0)
        self.assertEqual(store_rows[self.store.id]['payment_expense'], 100.0)
        self.assertEqual(store_rows[self.store.id]['goods_receipt_expense'], 10000.0)
        self.assertEqual(store_rows[self.store.id]['expense'], 10100.0)
        self.assertEqual(store_rows[self.store.id]['net'], -9750.0)
        self.assertEqual(store_rows[second_store.id]['income'], 600.0)
        self.assertEqual(store_rows[second_store.id]['payment_expense'], 90.0)
        self.assertEqual(store_rows[second_store.id]['goods_receipt_expense'], 20000.0)
        self.assertEqual(store_rows[second_store.id]['expense'], 20090.0)
        self.assertEqual(store_rows[second_store.id]['net'], -19490.0)

        selected_store_payload = self.client.get(reverse('api_report_finance'), {
            'from_date': from_day.isoformat(),
            'to_date': to_day.isoformat(),
            'store_id': self.store.id,
        }).json()
        self.assertEqual(selected_store_payload['summary']['total_income'], 350.0)
        self.assertEqual(selected_store_payload['summary']['payment_expense'], 100.0)
        self.assertEqual(selected_store_payload['summary']['goods_receipt_expense'], 10000.0)
        self.assertEqual(selected_store_payload['summary']['total_expense'], 10100.0)
        self.assertEqual(selected_store_payload['summary']['net_profit'], -9750.0)

        excel_response = self.client.get(reverse('export_finance_excel'), {
            'from_date': from_day.isoformat(),
            'to_date': to_day.isoformat(),
        })
        self.assertEqual(excel_response.status_code, 200)
        worksheet = load_workbook(
            BytesIO(excel_response.content),
            data_only=True,
        )['Thu chi']
        self.assertIn('Tổng phiếu chi: 190đ', worksheet['A3'].value)
        self.assertIn('Tổng hàng nhập: 30,000đ', worksheet['A3'].value)
        self.assertIn('Tổng chi = Tổng phiếu chi + Tổng hàng nhập: 30,190đ', worksheet['A4'].value)

        excel_rows = list(worksheet.iter_rows(values_only=True))
        imported_rows = {
            row[2]: row
            for row in excel_rows
            if row[1] == 'NHẬP HÀNG'
        }
        self.assertEqual(set(imported_rows), {
            'PN-RP-DONE-FROM',
            'PN-RP-DONE-TO',
            'PN-RP-SECOND-STORE',
        })
        self.assertEqual(imported_rows['PN-RP-SECOND-STORE'][6], 20000)
        total_rows = {
            row[1]: row[6]
            for row in excel_rows
            if row[1] in {
                'TỔNG THU',
                'TỔNG PHIẾU CHI',
                'TỔNG HÀNG NHẬP',
                'TỔNG CHI',
                'LÃI/LỖ',
            }
        }
        self.assertEqual(total_rows['TỔNG THU'], 950)
        self.assertEqual(total_rows['TỔNG PHIẾU CHI'], 190)
        self.assertEqual(total_rows['TỔNG HÀNG NHẬP'], 30000)
        self.assertEqual(total_rows['TỔNG CHI'], 30190)
        self.assertEqual(total_rows['LÃI/LỖ'], -29240)

    def test_finance_report_page_shows_expense_formula_cards(self):
        self.brand.owner = self.user
        self.brand.save(update_fields=['owner'])

        response = self.client.get(reverse('report_finance'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="payment_expense"')
        self.assertContains(response, 'Tổng phiếu chi')
        self.assertContains(response, 'id="goods_receipt_expense"')
        self.assertContains(response, 'Tổng hàng nhập')
        self.assertContains(response, 'id="total_expense"')
        self.assertContains(response, 'Tổng chi (phiếu chi + hàng nhập)')
        self.assertContains(response, 'id="order_debt_link"')
        self.assertContains(response, reverse('report_finance_order_debt'))
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'Xem bảng chi tiết')
        self.assertContains(response, "params.set('sort', 'debt_desc')")
        self.assertContains(response, 'id="payment_expense_link"')
        self.assertContains(response, reverse('payment_tbl'))
        self.assertNotContains(response, 'Xem bảng phiếu chi')
        self.assertContains(response, "params.set('status', '1')")
        self.assertContains(response, 'updatePaymentExpenseLink()')

    def test_finance_order_debt_page_only_lists_positive_debt_and_matches_card(self):
        self.brand.owner = self.user
        self.brand.save(update_fields=['owner'])
        today = date.today()
        outside_day = today - timedelta(days=40)
        debt_order = Order.objects.create(
            code='DH-DEBT-DETAIL-001',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=1,
            total_amount=1000,
            final_amount=1000,
            paid_amount=300,
            order_date=today,
            created_by=self.user,
        )
        Order.objects.create(
            code='DH-DEBT-PAID',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=500,
            final_amount=500,
            paid_amount=500,
            order_date=today,
            created_by=self.user,
        )
        Order.objects.create(
            code='DH-DEBT-OVERPAID',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=2,
            total_amount=500,
            final_amount=500,
            paid_amount=600,
            order_date=today,
            created_by=self.user,
        )
        Order.objects.create(
            code='DH-DEBT-CANCELED',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=6,
            payment_status=0,
            total_amount=900,
            final_amount=900,
            paid_amount=0,
            order_date=today,
            created_by=self.user,
        )
        Order.objects.create(
            code='DH-DEBT-OUTSIDE',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=0,
            total_amount=800,
            final_amount=800,
            paid_amount=0,
            order_date=outside_day,
            created_by=self.user,
        )
        params = {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        }

        page_response = self.client.get(reverse('report_finance_order_debt'), params)
        api_response = self.client.get(reverse('api_report_finance'), params)

        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, debt_order.code)
        self.assertContains(page_response, f'/order-tbl/?open_order={debt_order.id}')
        self.assertContains(page_response, '700đ')
        for excluded_code in (
            'DH-DEBT-PAID',
            'DH-DEBT-OVERPAID',
            'DH-DEBT-CANCELED',
            'DH-DEBT-OUTSIDE',
        ):
            self.assertNotContains(page_response, excluded_code)
        self.assertEqual(page_response.context['totals']['order_count'], 1)
        self.assertEqual(page_response.context['totals']['debt_amount'], 700)
        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.json()['summary']['order_debt'], 700.0)

    def test_finance_order_debt_page_is_paginated(self):
        self.brand.owner = self.user
        self.brand.save(update_fields=['owner'])
        today = date.today()
        Order.objects.bulk_create([
            Order(
                code=f'DH-DEBT-PAGE-{index:02d}',
                store=self.store,
                customer=self.customer,
                warehouse=self.warehouse,
                status=5,
                payment_status=0,
                total_amount=100,
                final_amount=100,
                paid_amount=0,
                order_date=today,
                created_by=self.user,
            )
            for index in range(31)
        ])

        response = self.client.get(reverse('report_finance_order_debt'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'page': 2,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].paginator.count, 31)
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertContains(response, 'Trang 2/2')
        self.assertContains(response, 'sort=debt_desc')

    def test_finance_order_debt_page_orders_highest_debt_first(self):
        self.brand.owner = self.user
        self.brand.save(update_fields=['owner'])
        today = date.today()
        yesterday = today - timedelta(days=1)
        Order.objects.create(
            code='DH-DEBT-LOW',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=1,
            total_amount=200,
            final_amount=200,
            paid_amount=100,
            order_date=today,
            created_by=self.user,
        )
        Order.objects.create(
            code='DH-DEBT-HIGH',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            payment_status=1,
            total_amount=1200,
            final_amount=1200,
            paid_amount=200,
            order_date=yesterday,
            created_by=self.user,
        )

        response = self.client.get(reverse('report_finance_order_debt'), {
            'from_date': yesterday.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['filters']['sort'], 'debt_desc')
        self.assertEqual(
            [order.code for order in response.context['page_obj']],
            ['DH-DEBT-HIGH', 'DH-DEBT-LOW'],
        )
        self.assertContains(response, 'Sắp xếp công nợ từ cao đến thấp')

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
        self.assertContains(response, 'class="inventory-product-edit-link" target="_blank"')
        self.assertContains(response, '/product-tbl/?edit_product_id=')
        self.assertContains(response, '_inventoryProductEditorOpened')
        self.assertContains(response, '<th>Tên sản phẩm</th>', count=1)
        self.assertNotContains(response, '<th>Mã SP</th>')
        self.assertContains(response, '<th title="Nhà cung cấp">NCC</th>', html=True)
        self.assertContains(response, '>Giá tính tồn</th>')
        self.assertContains(response, 'Dùng giá nhập')
        self.assertContains(response, 'colspan="13"')
        self.assertContains(response, 'var productIdentityHtml =')

    def test_api_inventory_report_exposes_product_supplier(self):
        from products.models import Supplier

        supplier = Supplier.objects.create(code='NCC-RP-STOCK', name='Nhà cung cấp báo cáo tồn')
        self.product.supplier = supplier
        self.product.save(update_fields=['supplier'])
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=4)

        response = self.client.get(reverse('api_report_inventory'))

        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.json()['data'] if item['product_id'] == self.product.id)
        self.assertEqual(row['supplier'], supplier.name)

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

    def test_inventory_value_uses_cost_then_import_without_negative_offset(self):
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
        import_fallback_product = Product.objects.create(
            store=self.store,
            code='SP-RP-VALUE-IMPORT',
            name='Sản phẩm dùng giá nhập',
            cost_price=0,
            import_price=80000,
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
        ProductStock.objects.create(product=import_fallback_product, warehouse=self.warehouse, quantity=2)
        ProductStock.objects.create(product=deleted_product, warehouse=self.warehouse, quantity=10)
        deleted_product.delete()

        payload = self.client.get(reverse('api_report_inventory')).json()
        rows = {row['product_code']: row for row in payload['data']}

        self.assertEqual(rows[positive_product.code]['stock_value'], 360000.0)
        self.assertEqual(rows[negative_product.code]['stock_value'], 0.0)
        self.assertEqual(rows[import_fallback_product.code]['cost_price'], 0.0)
        self.assertEqual(rows[import_fallback_product.code]['import_price'], 80000.0)
        self.assertEqual(rows[import_fallback_product.code]['valuation_price'], 80000.0)
        self.assertEqual(rows[import_fallback_product.code]['valuation_source'], 'import_price')
        self.assertEqual(rows[import_fallback_product.code]['stock_value'], 160000.0)
        self.assertNotIn(deleted_product.code, rows)
        self.assertEqual(payload['summary']['total_value'], 520000.0)

    def test_export_inventory_uses_import_price_when_cost_is_zero(self):
        product = Product.objects.create(
            store=self.store,
            code='SP-RP-EXPORT-IMPORT',
            name='Sản phẩm xuất tồn theo giá nhập',
            cost_price=0,
            import_price=90000,
            created_by=self.user,
        )
        ProductStock.objects.create(product=product, warehouse=self.warehouse, quantity=3)

        response = self.client.get(reverse('export_inventory_excel'))

        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content), data_only=True)
        sheet = workbook['Tồn kho']
        self.assertEqual(sheet['J4'].value, 'Giá tính tồn')
        product_row = next(
            row for row in range(5, sheet.max_row + 1)
            if sheet.cell(row=row, column=2).value == product.code
        )
        self.assertEqual(sheet.cell(row=product_row, column=10).value, 90000)
        self.assertEqual(sheet.cell(row=product_row, column=11).value, 270000)

    def test_inventory_filters_separate_root_categories_and_product_types(self):
        root = ProductCategory.objects.create(name='Danh mục thiết bị')
        product_type = ProductCategory.objects.create(name='Loại máy xay', parent=root)
        product = Product.objects.create(
            store=self.store,
            code='SP-RP-CATEGORY-TYPE',
            name='Máy xay báo cáo',
            category=product_type,
            created_by=self.user,
        )
        ProductStock.objects.create(product=product, warehouse=self.warehouse, quantity=2)

        payload = self.client.get(reverse('api_report_inventory')).json()
        self.assertIn(root.id, [item['id'] for item in payload['categories']])
        self.assertNotIn(product_type.id, [item['id'] for item in payload['categories']])
        self.assertIn(product_type.id, [item['id'] for item in payload['product_types']])

        by_category = self.client.get(reverse('api_report_inventory'), {
            'category_id': root.id,
        }).json()
        by_type = self.client.get(reverse('api_report_inventory'), {
            'product_type_id': product_type.id,
        }).json()
        self.assertIn(product.code, [item['product_code'] for item in by_category['data']])
        self.assertEqual([item['product_code'] for item in by_type['data']], [product.code])

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
        self.assertEqual(payload['timeline'][0]['period_key'], today.isoformat())
        self.assertEqual(
            {row['code'] for row in payload['order_details']},
            {created_orders[1].code, created_orders[2].code},
        )
        self.assertEqual(payload['filters_applied']['order_scope'], 'realized')

    def test_sales_report_daily_date_opens_filtered_order_list_in_new_tab(self):
        response = self.client.get(reverse('report_sales'))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertContains(response, 'id="supplier_sales_section"')
        self.assertContains(response, 'Báo cáo bán hàng theo nhà cung cấp')
        self.assertContains(response, 'id="supplier_sales_tbl"')
        self.assertContains(response, 'id="chart_supplier_consumption"')
        self.assertContains(response, 'id="chart_supplier_revenue"')
        self.assertContains(response, 'id="daily_chart_column"')
        self.assertNotContains(response, 'id="chart_products"')
        self.assertNotContains(response, 'function renderProductsPieChart(tp)')
        self.assertContains(response, 'Tỷ suất lợi nhuận')
        self.assertContains(response, 'id="ft_profit_margin"')
        self.assertContains(response, 'id="supplier_sales_filter"')
        self.assertContains(response, 'id="btn_clear_supplier_filter"')
        self.assertContains(response, 'Bấm vào thanh hoặc tên NCC để lọc bảng')
        self.assertContains(response, 'function renderSupplierBreakdown(rows,summary)')
        self.assertContains(response, 'function applySupplierFilter(key,scrollToTable)')
        self.assertContains(response, 'function bindSupplierChartInteraction(canvas,chart,rows)')
        self.assertLess(html.index('id="report_tbl"'), html.index('id="supplier_sales_section"'))
        self.assertLess(html.index('id="report_tbl"'), html.index('id="chart_supplier_consumption"'))
        self.assertLess(html.index('id="chart_supplier_consumption"'), html.index('id="supplier_sales_section"'))
        self.assertLess(html.index('id="supplier_sales_section"'), html.index('id="store_breakdown_section"'))
        self.assertContains(response, 'function getDailyOrdersUrl(dateKey)')
        self.assertContains(response, "'/order-tbl/?from_date='")
        self.assertContains(response, 'renderDailyOrderDate(d)')
        self.assertContains(response, 'sales-daily-order-link')
        self.assertContains(response, 'target="_blank" rel="noopener"')
        self.assertContains(response, 'id="top_products_limit"')
        self.assertContains(response, '10 sản phẩm')
        self.assertContains(response, '200 sản phẩm')
        self.assertContains(response, 'id="top_customers_limit"')
        self.assertContains(response, '5 khách hàng')
        self.assertContains(response, '200 khách hàng')
        self.assertContains(response, 'renderOverviewRankings();')
        self.assertContains(response, '(_overviewProductRows||[]).slice(0,productLimit)')
        self.assertContains(response, '(_overviewCustomerRows||[]).slice(0,customerLimit)')
        self.assertContains(response, 'id="order_detail_from_date"')
        self.assertContains(response, 'id="order_detail_to_date"')
        self.assertContains(response, 'function setOrderDetailCurrentMonth()')
        self.assertContains(response, 'new Date(today.getFullYear(),today.getMonth()+1,0)')
        self.assertContains(response, 'function getDateFilteredOrderDetails()')
        self.assertContains(response, "orderDate<from")
        self.assertContains(response, "orderDate>to")
        self.assertContains(response, "$('#orderDetailCollapse').on('shown.bs.collapse', refreshOrderDetails)")
        self.assertContains(response, "$('#order_detail_tbl tbody').empty()")

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

    def test_api_report_sales_does_not_warn_for_fully_returned_loss_order(self):
        today = date.today()
        order = Order.objects.create(
            code='DH-RP-FULL-RETURN-LOSS',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
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
            cost_price=130,
            total_price=100,
        )
        order_return = OrderReturn.objects.create(
            code='TH-RP-FULL-RETURN-LOSS',
            order=order,
            customer=self.customer,
            warehouse=self.warehouse,
            status=2,
            total_refund=100,
            return_date=today,
            created_by=self.user,
        )
        OrderReturnItem.objects.create(
            order_return=order_return,
            product=self.product,
            quantity=1,
            unit_price=100,
            total_price=100,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = next(item for item in payload['order_details'] if item['code'] == order.code)
        self.assertFalse(row['is_loss'])
        self.assertEqual(row['loss_products'], [])
        self.assertEqual(payload['summary']['loss_count'], 0)

        loss_response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
            'profit_filter': 'loss',
        })
        self.assertEqual(loss_response.status_code, 200)
        loss_payload = loss_response.json()
        self.assertEqual(loss_payload['summary']['loss_count'], 0)
        self.assertNotIn(order.code, [item['code'] for item in loss_payload['order_details']])

    def test_api_report_sales_uses_value_only_return_for_legacy_full_return(self):
        today = date.today()
        order = Order.objects.create(
            code='DH-RP-LEGACY-FULL-RETURN',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
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
            cost_price=130,
            total_price=100,
        )
        OrderReturn.objects.create(
            code='TH-RP-LEGACY-FULL-RETURN',
            order=order,
            customer=self.customer,
            warehouse=self.warehouse,
            status=2,
            return_amount=100,
            total_refund=100,
            return_date=today,
            created_by=self.user,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = next(item for item in payload['order_details'] if item['code'] == order.code)
        self.assertFalse(row['is_loss'])
        self.assertEqual(row['loss_products'], [])

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
        self.assertEqual(payload['daily'][0]['profit_margin'], 53.3)

    def test_api_report_sales_groups_multiple_products_and_returns_by_supplier(self):
        today = date.today()
        supplier_a = Supplier.objects.create(code='NCC-RP-SALES-A', name='NCC bán hàng A')
        supplier_b = Supplier.objects.create(code='NCC-RP-SALES-B', name='NCC bán hàng B')
        product_a1 = Product.objects.create(
            store=self.store,
            supplier=supplier_a,
            code='SP-RP-NCC-A1',
            name='Sản phẩm NCC A1',
            created_by=self.user,
        )
        product_a2 = Product.objects.create(
            store=self.store,
            supplier=supplier_a,
            code='SP-RP-NCC-A2',
            name='Sản phẩm NCC A2',
            created_by=self.user,
        )
        product_b = Product.objects.create(
            store=self.store,
            supplier=supplier_b,
            code='SP-RP-NCC-B',
            name='Sản phẩm NCC B',
            created_by=self.user,
        )
        first_order = Order.objects.create(
            code='DH-RP-NCC-1',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            total_amount=550,
            final_amount=550,
            order_date=today,
            created_by=self.user,
        )
        for product, quantity, total_price, cost_price in (
            (product_a1, 2, 200, 60),
            (product_a2, 3, 150, 20),
            (product_b, 1, 200, 100),
        ):
            OrderItem.objects.create(
                order=first_order,
                product=product,
                quantity=quantity,
                unit_price=total_price / quantity,
                cost_price=cost_price,
                total_price=total_price,
            )
        second_order = Order.objects.create(
            code='DH-RP-NCC-2',
            store=self.store,
            customer=self.customer,
            warehouse=self.warehouse,
            status=5,
            total_amount=100,
            final_amount=100,
            order_date=today,
            created_by=self.user,
        )
        OrderItem.objects.create(
            order=second_order,
            product=product_a1,
            quantity=1,
            unit_price=100,
            cost_price=60,
            total_price=100,
        )
        order_return = OrderReturn.objects.create(
            code='TH-RP-NCC-1',
            order=first_order,
            customer=self.customer,
            warehouse=self.warehouse,
            status=2,
            total_refund=50,
            return_date=today,
            created_by=self.user,
        )
        OrderReturnItem.objects.create(
            order_return=order_return,
            product=product_a2,
            quantity=1,
            unit_price=50,
            total_price=50,
        )

        response = self.client.get(reverse('api_report_sales'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        rows = response.json()['supplier_breakdown']
        supplier_summary = response.json()['supplier_summary']
        self.assertEqual([row['supplier'] for row in rows], [supplier_a.name, supplier_b.name])
        self.assertEqual(supplier_summary['supplier_count'], 2)
        self.assertEqual(supplier_summary['product_count'], 3)
        self.assertEqual(supplier_summary['order_count'], 2)
        supplier_a_row = rows[0]
        self.assertEqual(supplier_a_row['product_count'], 2)
        self.assertEqual(supplier_a_row['order_count'], 2)
        self.assertEqual(supplier_a_row['sold_quantity'], 6.0)
        self.assertEqual(supplier_a_row['returned_quantity'], 1.0)
        self.assertEqual(supplier_a_row['net_quantity'], 5.0)
        self.assertEqual(supplier_a_row['net_revenue'], 400.0)
        self.assertEqual(supplier_a_row['cost'], 220.0)
        self.assertEqual(supplier_a_row['profit'], 180.0)
        self.assertEqual(supplier_a_row['contribution'], 66.7)
        self.assertEqual(supplier_a_row['top_products'][0]['name'], product_a1.name)
        self.assertEqual(supplier_a_row['top_products'][0]['net_quantity'], 3.0)

        export_response = self.client.get(reverse('export_sales_excel'), {
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })
        workbook = load_workbook(BytesIO(export_response.content), data_only=True)
        self.assertIn('Bán hàng theo NCC', workbook.sheetnames)
        supplier_sheet = workbook['Bán hàng theo NCC']
        self.assertEqual(supplier_sheet['B2'].value, supplier_a.name)
        self.assertEqual(supplier_sheet['G2'].value, 5)
        self.assertEqual(supplier_sheet['H2'].value, 400)

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
