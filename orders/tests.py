import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from customers.models import Customer
from finance.models import CashBook, Payment, PaymentMethodOption, Receipt
from finance.services import update_order_payment_status
from orders.models import (
    Order, OrderEditHistory, OrderItem, OrderReturn, OrderReturnExchangeItem,
    OrderReturnItem, Quotation,
)
from products.models import ComboItem, Product, ProductStock, ProductVariant, Warehouse
from system_management.models import Brand, BusinessConfig, PrintTemplate, Store, UserProfile


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

    def test_quick_create_customer_persists_customer_kind(self):
        response = self.client.post(
            reverse('api_quick_create_customer'),
            data=json.dumps({
                'name': 'Khách tạo nhanh',
                'phone': '0909555666',
                'customer_kind': Customer.CUSTOMER_KIND_WHOLESALE,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        customer = Customer.objects.get(code=payload['customer']['code'])
        self.assertEqual(customer.customer_kind, Customer.CUSTOMER_KIND_WHOLESALE)
        self.assertEqual(customer.store_id, self.store.id)

    def test_products_select_keeps_negative_stock_values(self):
        ProductStock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=-3,
        )

        response = self.client.get(reverse('api_get_products_for_select'))

        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.json()['data'] if item['id'] == self.product.id)
        warehouse_key = str(self.warehouse.id)
        self.assertEqual(row['stocks'][warehouse_key], -3.0)
        self.assertEqual(row['sellable_stocks'][warehouse_key], -3.0)
        self.assertEqual(row['total_stock'], -3.0)
        self.assertEqual(row['total_sellable_stock'], -3.0)

    def test_next_order_code_skips_soft_deleted_order(self):
        order = self._create_order(code='DH-016', status=0)
        order.delete()

        response = self.client.get(reverse('api_next_order_code'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 'DH-017')

    def test_save_order_auto_advances_when_requested_code_belongs_to_deleted_order(self):
        order = self._create_order(code='DH-016', status=0)
        order.delete()

        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps({
                'code': 'DH-016',
                'customer_id': self.customer.id,
                'warehouse_id': self.warehouse.id,
                'order_date': date.today().isoformat(),
                'discount_amount': 0,
                'shipping_fee': 0,
                'status': 0,
                'note': '',
                'tags': '',
                'pay_mode': 'none',
                'payment_amount': 0,
                'payment_lines': [],
                'items': [],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())
        self.assertEqual(payload['order_code'], 'DH-017')

    def test_products_select_exposes_product_retail_price_as_default_price(self):
        self.product.selling_price = 12000000
        self.product.save(update_fields=['selling_price'])
        ProductVariant.objects.create(
            product=self.product,
            size_name='Legacy',
            sku='SP-ORDER-001-LEGACY',
            selling_price=10990000,
        )

        response = self.client.get(reverse('api_get_products_for_select'))

        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.json()['data'] if item['id'] == self.product.id)
        self.assertEqual(row['retail_price'], 12000000.0)
        self.assertEqual(row['price'], 12000000.0)
        self.assertEqual(row['variants'][0]['selling_price'], 10990000.0)
        self.assertEqual(row['variants'][0]['retail_price'], 12000000.0)

    def test_products_select_exposes_combo_components_and_component_based_stock(self):
        self.product.cost_price = 100
        self.product.selling_price = 150
        self.product.save(update_fields=['cost_price', 'selling_price'])
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=5)
        combo = Product.objects.create(
            store=self.store,
            code='CB-ORDER-001',
            name='Combo bán hàng',
            unit='Bo',
            is_combo=True,
            cost_price=200,
            selling_price=250,
            created_by=self.user,
        )
        ComboItem.objects.create(combo=combo, product=self.product, quantity=2)

        response = self.client.get(reverse('api_get_products_for_select'))

        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.json()['data'] if item['id'] == combo.id)
        warehouse_key = str(self.warehouse.id)
        self.assertTrue(row['is_combo'])
        self.assertEqual(row['stocks'][warehouse_key], 2.0)
        self.assertEqual(row['total_stock'], 2.0)
        self.assertEqual(row['combo_items'][0]['product_code'], self.product.code)
        self.assertEqual(row['combo_items'][0]['unit'], self.product.unit)
        self.assertEqual(row['combo_items'][0]['line_cost'], 200.0)
        self.assertEqual(row['combo_items'][0]['total_stock'], 5.0)

    def test_get_orders_returns_paginated_meta(self):
        created_orders = []
        for idx in range(12):
            created_orders.append(self._create_order(code=f'DH-PAGE-{idx:02d}', status=1))

        response = self.client.get(reverse('api_get_orders'), {'page': 2, 'page_size': 10})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['meta']['page'], 2)
        self.assertEqual(payload['meta']['page_size'], 10)
        self.assertEqual(payload['meta']['total_filtered_count'], 12)
        self.assertEqual(payload['meta']['total_pages'], 2)
        self.assertEqual(payload['meta']['start_index'], 11)
        self.assertEqual(payload['meta']['end_index'], 12)
        self.assertEqual(len(payload['data']), 2)
        expected_ids = [order.id for order in list(reversed(created_orders))[10:12]]
        self.assertEqual([row['id'] for row in payload['data']], expected_ids)

    def test_get_orders_filters_by_product_on_server(self):
        other_same_store_product = Product.objects.create(
            store=self.store,
            code='SP-ORDER-FILTER',
            name='Sản phẩm lọc đơn',
            created_by=self.user,
        )
        first_order = self._create_order(code='DH-FILTER-001', status=1)
        second_order = self._create_order(code='DH-FILTER-002', status=1)
        OrderItem.objects.create(order=first_order, product=self.product, quantity=1, unit_price=100, total_price=100)
        OrderItem.objects.create(order=second_order, product=other_same_store_product, quantity=1, unit_price=100, total_price=100)

        response = self.client.get(reverse('api_get_orders'), {'product': 'FILTER'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['meta']['total_filtered_count'], 1)
        self.assertEqual([row['id'] for row in payload['data']], [second_order.id])

    def test_get_orders_status_counts_ignore_active_status_filter(self):
        self._create_order(code='DH-COUNT-001', status=1)
        self._create_order(code='DH-COUNT-002', status=1)
        completed_order = self._create_order(code='DH-COUNT-003', status=5)

        response = self.client.get(reverse('api_get_orders'), {'status': 1})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(all(row['status'] == 1 for row in payload['data']))
        self.assertEqual(payload['meta']['status_counts']['all'], 3)
        self.assertEqual(payload['meta']['status_counts']['1'], 2)
        self.assertEqual(payload['meta']['status_counts']['5'], 1)
        self.assertNotIn(completed_order.id, [row['id'] for row in payload['data']])

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
                'payment_lines': [{
                    'amount': 100,
                    'payment_method': 1,
                    'payment_method_option_id': self.payment_method.id,
                    'cash_book_id': self.cashbook.id,
                }],
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
        self.cashbook.refresh_from_db()
        self.assertEqual(float(self.cashbook.balance), 1000100.0)

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

    def test_exported_order_rejects_price_change_and_item_removal(self):
        order = self._create_order(code='DH-EXPORT-LOCKED', status=4)
        item = OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=100,
            total_price=100,
        )

        base_payload = {
            'id': order.id,
            'code': order.code,
            'customer_id': self.customer.id,
            'warehouse_id': self.warehouse.id,
            'order_date': order.order_date.isoformat(),
            'discount_amount': 0,
            'shipping_fee': 0,
            'status': 4,
            'note': '',
            'tags': '',
            'pay_mode': 'none',
            'payment_amount': 0,
            'payment_lines': [],
        }

        changed_price_payload = {
            **base_payload,
            'items': [{
                'product_id': self.product.id,
                'variant_id': None,
                'quantity': 1,
                'unit_price': 90,
                'discount_percent': 0,
            }],
        }
        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps(changed_price_payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('đã xuất kho', payload['message'])
        self.assertIn('sản phẩm/giá/số lượng', payload['message'])
        item.refresh_from_db()
        self.assertEqual(item.unit_price, 100)

        removed_item_payload = {**base_payload, 'items': []}
        response = self.client.post(
            reverse('api_save_order'),
            data=json.dumps(removed_item_payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('đã xuất kho', payload['message'])
        self.assertEqual(order.items.count(), 1)

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

    def test_exported_order_note_remains_locked(self):
        order = self._create_order(code='DH-EXPORT-NOTE', status=4)

        response = self.client.post(
            reverse('api_update_order_note'),
            data=json.dumps({'id': order.id, 'note': 'Không được sửa sau xuất kho'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('xuất kho', payload['message'])

        order.refresh_from_db()
        self.assertNotEqual(order.note, 'Không được sửa sau xuất kho')

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

    def test_bulk_collect_accepts_line_amounts_across_customers(self):
        other_customer_same_store = Customer.objects.create(
            store=self.store,
            code='KH003',
            name='Customer C',
            created_by=self.user,
        )
        first_order = self._create_order(code='DH-BULK-LINE-001', customer=self.customer)
        second_order = self._create_order(
            code='DH-BULK-LINE-002',
            customer=other_customer_same_store,
        )
        second_order.final_amount = 200
        second_order.save(update_fields=['final_amount'])

        response = self.client.post(
            reverse('api_bulk_collect_orders'),
            data=json.dumps({
                'ids': [first_order.id, second_order.id],
                'payment_method_option_id': self.payment_method.id,
                'payments': [
                    {'order_id': first_order.id, 'amount': 40},
                    {'order_id': second_order.id, 'amount': 200},
                ],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())
        self.assertEqual(payload['collected_count'], 2)
        self.assertEqual(payload['total_collected'], 240.0)

        first_order.refresh_from_db()
        second_order.refresh_from_db()
        self.assertEqual(float(first_order.paid_amount), 40.0)
        self.assertEqual(first_order.payment_status, 1)
        self.assertEqual(float(second_order.paid_amount), 200.0)
        self.assertEqual(second_order.payment_status, 2)

    def test_collect_order_payment_accepts_multiple_methods_without_saving_order(self):
        order = self._create_order(code='DH-COLLECT-ONE-001', status=1)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=100,
            total_price=100,
        )

        response = self.client.post(
            reverse('api_collect_order_payment'),
            data=json.dumps({
                'order_id': order.id,
                'payment_lines': [
                    {
                        'amount': 40,
                        'payment_method': 1,
                        'payment_method_option_id': self.payment_method.id,
                        'cash_book_id': self.cashbook.id,
                    },
                    {
                        'amount': 60,
                        'payment_method': 1,
                        'payment_method_option_id': self.payment_method.id,
                        'cash_book_id': self.cashbook.id,
                    },
                ],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        order.refresh_from_db()
        self.assertEqual(order.status, 1)
        self.assertEqual(order.payment_status, 2)
        self.assertEqual(float(order.paid_amount), 100.0)
        self.assertEqual(Receipt.objects.filter(order=order, status=1).count(), 2)
        self.cashbook.refresh_from_db()
        self.assertEqual(float(self.cashbook.balance), 1000100.0)

    def test_collect_order_payment_can_be_called_repeatedly_without_saving_order(self):
        order = self._create_order(code='DH-COLLECT-REPEAT-001', status=1)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=100,
            total_price=100,
        )

        first_response = self.client.post(
            reverse('api_collect_order_payment'),
            data=json.dumps({
                'order_id': order.id,
                'payment_lines': [{
                    'amount': 40,
                    'payment_method': 1,
                    'payment_method_option_id': self.payment_method.id,
                    'cash_book_id': self.cashbook.id,
                }],
            }),
            content_type='application/json',
        )
        second_response = self.client.post(
            reverse('api_collect_order_payment'),
            data=json.dumps({
                'order_id': order.id,
                'payment_lines': [{
                    'amount': 60,
                    'payment_method': 1,
                    'payment_method_option_id': self.payment_method.id,
                    'cash_book_id': self.cashbook.id,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(first_response.status_code, 200)
        first_payload = first_response.json()
        self.assertEqual(first_payload['status'], 'ok', msg=first_response.content.decode())
        self.assertEqual(first_payload['paid_amount'], 40.0)
        self.assertEqual(first_payload['remaining_amount'], 60.0)
        self.assertEqual(first_payload['payment_status'], 1)

        self.assertEqual(second_response.status_code, 200)
        second_payload = second_response.json()
        self.assertEqual(second_payload['status'], 'ok', msg=second_response.content.decode())
        self.assertEqual(second_payload['paid_amount'], 100.0)
        self.assertEqual(second_payload['remaining_amount'], 0.0)
        self.assertEqual(second_payload['payment_status'], 2)

        order.refresh_from_db()
        self.assertEqual(float(order.paid_amount), 100.0)
        self.assertEqual(order.payment_status, 2)
        self.assertEqual(Receipt.objects.filter(order=order, status=1).count(), 2)
        history_summaries = list(
            OrderEditHistory.objects.filter(order=order, action='payment').values_list('summary', flat=True)
        )
        self.assertTrue(any('còn phải thu 60' in summary for summary in history_summaries))
        self.assertTrue(any('đã thanh toán đủ' in summary for summary in history_summaries))

    def test_export_order_stock_is_independent_from_payment(self):
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=5)
        order = self._create_order(code='DH-EXPORT-NO-PAY-001', status=1)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=50,
            total_price=100,
        )

        response = self.client.post(
            reverse('api_export_order_stock'),
            data=json.dumps({'order_id': order.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        order.refresh_from_db()
        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(order.status, 4)
        self.assertEqual(order.payment_status, 0)
        self.assertEqual(float(stock.quantity), 3.0)
        self.assertFalse(Receipt.objects.filter(order=order).exists())

    def test_update_order_status_api_moves_steps_without_full_order_save(self):
        order = self._create_order(code='DH-STATUS-FAST-001', status=1)

        first_response = self.client.post(
            reverse('api_update_order_status'),
            data=json.dumps({'order_id': order.id, 'status': 2}),
            content_type='application/json',
        )
        second_response = self.client.post(
            reverse('api_update_order_status'),
            data=json.dumps({'order_id': order.id, 'status': 3}),
            content_type='application/json',
        )

        self.assertEqual(first_response.json()['status'], 'ok', msg=first_response.content.decode())
        self.assertEqual(second_response.json()['status'], 'ok', msg=second_response.content.decode())
        order.refresh_from_db()
        self.assertEqual(order.status, 3)

    def test_save_order_history_describes_item_quantity_change(self):
        order = self._create_order(code='DH-HISTORY-ITEM-001', status=1)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=50,
            total_price=100,
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
                    'quantity': 3,
                    'unit_price': 50,
                    'discount_percent': 0,
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        history = OrderEditHistory.objects.filter(order=order, action='update').first()
        self.assertIsNotNone(history)
        self.assertIn('Sửa SP', history.summary)
        self.assertIn('SL 2 → 3', history.summary)
        self.assertIn('Tổng thanh toán: 100đ → 150đ', history.summary)
        self.assertLess(
            history.summary.index('Sửa SP'),
            history.summary.index('Tổng thanh toán'),
        )

    def test_save_order_history_prioritizes_deleted_item_before_amount_change(self):
        deleted_product = Product.objects.create(
            store=self.store,
            code='SP-ORDER-DELETE',
            name='Sản phẩm bị xóa khỏi đơn',
            created_by=self.user,
        )
        order = self._create_order(code='DH-HISTORY-DELETE-001', status=1)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=100,
            total_price=100,
        )
        OrderItem.objects.create(
            order=order,
            product=deleted_product,
            quantity=1,
            unit_price=50,
            total_price=50,
        )
        order.total_amount = 150
        order.final_amount = 150
        order.save(update_fields=['total_amount', 'final_amount'])

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

        history = OrderEditHistory.objects.filter(order=order, action='update').first()
        self.assertIsNotNone(history)
        self.assertIn('Xóa SP "SP-ORDER-DELETE - Sản phẩm bị xóa khỏi đơn"', history.summary)
        self.assertIn('thành tiền 50đ', history.summary)
        self.assertIn('Tổng thanh toán: 150đ → 100đ', history.summary)
        self.assertLess(
            history.summary.index('Xóa SP'),
            history.summary.index('Tổng thanh toán'),
        )

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

    def test_pos_checkout_without_payment_stays_exported(self):
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=1)

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
                'paid_amount': 0,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())

        order = Order.objects.get(id=payload['order_id'])
        self.assertEqual(order.status, 4)
        self.assertEqual(order.payment_status, 0)
        self.assertEqual(float(order.paid_amount), 0.0)
        self.assertEqual(order.receipts.count(), 0)

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

    def test_save_order_return_with_items_restocks_exported_order(self):
        order = self._create_order(code='DH-RETURN-ITEMS-001', status=4)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=50,
            total_price=100,
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=3)

        response = self.client.post(
            reverse('api_save_order_return'),
            data=json.dumps({
                'code': '',
                'order_id': order.id,
                'return_date': date.today().isoformat(),
                'status': 2,
                'reason': 'Khách trả một phần',
                'payment_method_option_id': self.payment_method.id,
                'items': [{
                    'product_id': self.product.id,
                    'quantity': 1,
                    'unit_price': 45,
                    'reason': 'Hàng lỗi',
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())
        self.assertTrue(payload['return_code'].startswith('TH-'))

        order_return = OrderReturn.objects.get(id=payload['return_id'])
        return_item = OrderReturnItem.objects.get(order_return=order_return)
        self.assertEqual(return_item.product_id, self.product.id)
        self.assertEqual(return_item.quantity, 1)
        self.assertEqual(float(order_return.total_refund), 45.0)
        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(float(stock.quantity), 4.0)
        refund_payment = Payment.objects.get(reference=f'ORDER_RETURN:{order_return.id}')
        self.assertEqual(float(refund_payment.amount), 45.0)
        self.cashbook.refresh_from_db()
        self.assertEqual(float(self.cashbook.balance), 999955.0)

    def test_save_order_return_with_exchange_items_collects_difference_and_moves_stock(self):
        exchange_product = Product.objects.create(
            store=self.store,
            code='SP-EXCHANGE-001',
            name='Sản phẩm đổi mới',
            created_by=self.user,
        )
        order = self._create_order(code='DH-RETURN-EXCHANGE-001', status=4)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=50,
            total_price=100,
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=3)
        ProductStock.objects.create(product=exchange_product, warehouse=self.warehouse, quantity=5)

        response = self.client.post(
            reverse('api_save_order_return'),
            data=json.dumps({
                'code': 'TH-EXCHANGE-001',
                'order_id': order.id,
                'return_date': date.today().isoformat(),
                'status': 2,
                'reason': 'Khách đổi sang mẫu khác',
                'payment_method_option_id': self.payment_method.id,
                'items': [{
                    'product_id': self.product.id,
                    'quantity': 1,
                    'unit_price': 45,
                    'reason': 'Hàng lỗi',
                }],
                'exchange_items': [{
                    'product_id': exchange_product.id,
                    'quantity': 1,
                    'unit_price': 70,
                    'discount_percent': 0,
                    'note': 'Đổi mẫu mới',
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())
        self.assertEqual(payload['total_refund'], 0.0)
        self.assertEqual(payload['amount_due'], 25.0)

        order_return = OrderReturn.objects.get(code='TH-EXCHANGE-001')
        self.assertEqual(float(order_return.return_amount), 45.0)
        self.assertEqual(float(order_return.exchange_amount), 70.0)
        self.assertEqual(float(order_return.amount_due), 25.0)
        self.assertEqual(OrderReturnExchangeItem.objects.filter(order_return=order_return).count(), 1)
        self.assertIsNotNone(order_return.exchange_order_id)
        exchange_order = order_return.exchange_order
        self.assertEqual(exchange_order.customer_id, order.customer_id)
        self.assertEqual(exchange_order.warehouse_id, order.warehouse_id)
        self.assertEqual(float(exchange_order.total_amount), 70.0)
        self.assertEqual(float(exchange_order.discount_amount), 45.0)
        self.assertEqual(float(exchange_order.final_amount), 25.0)
        self.assertEqual(exchange_order.items.count(), 1)
        returned_stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        exchanged_stock = ProductStock.objects.get(product=exchange_product, warehouse=self.warehouse)
        self.assertEqual(float(returned_stock.quantity), 4.0)
        self.assertEqual(float(exchanged_stock.quantity), 4.0)

        due_receipt = Receipt.objects.get(reference=f'ORDER_RETURN_DUE:{order_return.id}')
        self.assertEqual(float(due_receipt.amount), 25.0)
        self.assertEqual(due_receipt.order_id, exchange_order.id)
        self.assertFalse(Payment.objects.filter(reference=f'ORDER_RETURN:{order_return.id}', status=1).exists())
        self.cashbook.refresh_from_db()
        self.assertEqual(float(self.cashbook.balance), 1000025.0)
        history = OrderEditHistory.objects.filter(order=order, action='return').first()
        self.assertIn('hàng đổi', history.summary)
        self.assertIn('khách còn thanh toán 25đ', history.summary)
        self.assertIn(exchange_order.code, history.summary)

        orders_payload = self.client.get(reverse('api_get_orders')).json()['data']
        original_row = next(row for row in orders_payload if row['id'] == order.id)
        exchange_row = next(row for row in orders_payload if row['id'] == exchange_order.id)
        self.assertTrue(original_row['has_returns'])
        self.assertTrue(original_row['has_exchange_returns'])
        self.assertEqual(original_row['returns'][0]['code'], order_return.code)
        self.assertEqual(original_row['returns'][0]['exchange_order_id'], exchange_order.id)
        self.assertTrue(exchange_row['is_exchange_order'])
        self.assertEqual(exchange_row['exchange_source_return_code'], order_return.code)
        self.assertEqual(exchange_row['exchange_original_order_code'], order.code)

        detail_payload = self.client.get(reverse('api_get_order_detail'), {'id': order.id}).json()
        self.assertEqual(detail_payload['status'], 'ok')
        self.assertEqual(detail_payload['order']['returns'][0]['exchange_order_code'], exchange_order.code)

    def test_save_order_return_allows_standalone_compensation_refund(self):
        order = self._create_order(code='DH-RETURN-COMPENSATION', status=5)

        response = self.client.post(
            reverse('api_save_order_return'),
            data=json.dumps({
                'code': 'TH-COMPENSATION-001',
                'order_id': order.id,
                'return_date': date.today().isoformat(),
                'status': 2,
                'reason': 'Hàng vỡ cần đền bù',
                'payment_method_option_id': self.payment_method.id,
                'compensation_amount': 30,
                'items': [],
                'exchange_items': [],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())
        self.assertEqual(payload['total_refund'], 30.0)
        self.assertEqual(payload['amount_due'], 0.0)

        order_return = OrderReturn.objects.get(code='TH-COMPENSATION-001')
        self.assertEqual(float(order_return.compensation_amount), 30.0)
        self.assertEqual(order_return.items.count(), 0)
        self.assertEqual(order_return.exchange_items.count(), 0)
        refund_payment = Payment.objects.get(reference=f'ORDER_RETURN:{order_return.id}')
        self.assertEqual(float(refund_payment.amount), 30.0)
        self.cashbook.refresh_from_db()
        self.assertEqual(float(self.cashbook.balance), 999970.0)

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
        self.assertEqual(order.status, 5)
        self.assertEqual(order.receipts.count(), 0)

    def test_payment_sync_demotes_completed_order_when_unpaid(self):
        order = self._create_order(code='DH-COMPLETE-UNPAID', status=5)

        update_order_payment_status(order)

        order.refresh_from_db()
        self.assertEqual(order.status, 4)
        self.assertEqual(order.payment_status, 0)

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

    def test_print_order_can_show_and_hide_combo_components(self):
        combo = Product.objects.create(
            store=self.store,
            code='CB-PRINT-001',
            name='Combo in đơn',
            unit='Bo',
            is_combo=True,
            created_by=self.user,
        )
        ComboItem.objects.create(combo=combo, product=self.product, quantity=2)
        order = self._create_order(code='DH-COMBO-PRINT', status=5)
        OrderItem.objects.create(
            order=order,
            product=combo,
            quantity=1,
            unit_price=100,
            total_price=100,
        )

        response = self.client.get(reverse('api_print_order'), {'id': order.id, 'type': 'a4', 'source': 'order'})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Combo in đơn', content)
        self.assertIn('SP-ORDER-001 - Sản phẩm test đơn hàng', content)

        PrintTemplate.objects.update_or_create(
            brand=self.brand,
            template_type='a4',
            defaults={'title': 'Hóa đơn A4', 'show_combo_components': False},
        )
        hidden_response = self.client.get(reverse('api_print_order'), {'id': order.id, 'type': 'a4', 'source': 'order'})

        self.assertEqual(hidden_response.status_code, 200)
        hidden_content = hidden_response.content.decode()
        self.assertIn('Combo in đơn', hidden_content)
        self.assertNotIn('SP-ORDER-001 - Sản phẩm test đơn hàng', hidden_content)

    def test_print_order_shows_product_note_below_item_name(self):
        self.product.note = 'Tặng kèm dây nguồn'
        self.product.save(update_fields=['note'])
        order = self._create_order(code='DH-PRINT-NOTE', status=5)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=100,
            total_price=100,
        )

        response = self.client.get(reverse('api_print_order'), {'id': order.id, 'type': 'a4', 'source': 'order'})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Sản phẩm test đơn hàng', content)
        self.assertIn('Tặng kèm dây nguồn', content)
