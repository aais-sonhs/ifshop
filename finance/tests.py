import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from customers.models import Customer
from finance.models import CashBook, Payment, Receipt
from orders.models import Order
from products.models import GoodsReceipt, Supplier, Warehouse
from system_management.models import Brand, Store, UserProfile


class FinanceFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name='Finance Brand')
        cls.store = Store.objects.create(brand=cls.brand, name='Finance Store A', code='FSA')
        cls.other_store = Store.objects.create(brand=cls.brand, name='Finance Store B', code='FSB')

        cls.user = User.objects.create_user(username='finance_a', password='pass123')
        cls.other_user = User.objects.create_user(username='finance_b', password='pass123')
        UserProfile.objects.create(user=cls.user, store=cls.store)
        UserProfile.objects.create(user=cls.other_user, store=cls.other_store)

        cls.customer = Customer.objects.create(
            store=cls.store,
            code='FKH001',
            name='Finance Customer A',
            created_by=cls.user,
        )
        cls.other_customer = Customer.objects.create(
            store=cls.other_store,
            code='FKH002',
            name='Finance Customer B',
            created_by=cls.other_user,
        )

        cls.supplier = Supplier.objects.create(
            code='NCC001',
            name='Supplier A',
            created_by=cls.user,
        )
        cls.warehouse = Warehouse.objects.create(store=cls.store, code='FKHO-A', name='Kho Finance A')
        cls.other_warehouse = Warehouse.objects.create(
            store=cls.other_store,
            code='FKHO-B',
            name='Kho Finance B',
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _create_order(self, code, store=None, customer=None, warehouse=None, created_by=None):
        return Order.objects.create(
            code=code,
            store=store or self.store,
            customer=customer or self.customer,
            warehouse=warehouse or self.warehouse,
            total_amount=100,
            final_amount=100,
            order_date=date.today(),
            created_by=created_by or self.user,
        )

    def _create_goods_receipt(self, code, store=None, supplier=None, warehouse=None, created_by=None):
        return GoodsReceipt.objects.create(
            code=code,
            supplier=supplier or self.supplier,
            warehouse=warehouse or self.warehouse,
            total_amount=100,
            receipt_date=date.today(),
            created_by=created_by or self.user,
        )

    def test_delete_payment_refunds_cashbook_balance(self):
        cash_book = CashBook.objects.create(name='Quỹ A', balance=Decimal('800'))
        payment = Payment.objects.create(
            code='PC-001',
            store=self.store,
            cash_book=cash_book,
            amount=Decimal('200'),
            payment_date=date.today(),
            status=1,
            created_by=self.user,
        )

        response = self.client.post(
            reverse('api_delete_payment'),
            data=json.dumps({'id': payment.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())

        cash_book.refresh_from_db()
        deleted_payment = Payment.all_objects.get(id=payment.id)
        self.assertEqual(cash_book.balance, Decimal('1000'))
        self.assertTrue(deleted_payment.is_deleted)

    def test_save_receipt_rejects_foreign_order(self):
        other_order = self._create_order(
            code='DH-FOREIGN-001',
            store=self.other_store,
            customer=self.other_customer,
            warehouse=self.other_warehouse,
            created_by=self.other_user,
        )

        response = self.client.post(
            reverse('api_save_receipt'),
            data=json.dumps({
                'code': 'PT-FOREIGN-001',
                'order_id': other_order.id,
                'amount': 100,
                'receipt_date': date.today().isoformat(),
                'status': 0,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Không tìm thấy đơn hàng', payload['message'])
        self.assertFalse(Receipt.objects.filter(code='PT-FOREIGN-001').exists())

    def test_save_receipt_rejects_foreign_customer_without_order(self):
        response = self.client.post(
            reverse('api_save_receipt'),
            data=json.dumps({
                'code': 'PT-FOREIGN-CUSTOMER',
                'customer_id': self.other_customer.id,
                'amount': 100,
                'receipt_date': date.today().isoformat(),
                'status': 0,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Khách hàng', payload['message'])
        self.assertFalse(Receipt.objects.filter(code='PT-FOREIGN-CUSTOMER').exists())

    def test_save_receipt_rejects_customer_that_mismatches_order(self):
        order = self._create_order(code='DH-RECEIPT-MISMATCH')

        response = self.client.post(
            reverse('api_save_receipt'),
            data=json.dumps({
                'code': 'PT-MISMATCH-CUSTOMER',
                'order_id': order.id,
                'customer_id': self.other_customer.id,
                'amount': 100,
                'receipt_date': date.today().isoformat(),
                'status': 0,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Khách hàng', payload['message'])
        self.assertFalse(Receipt.objects.filter(code='PT-MISMATCH-CUSTOMER').exists())

    def test_save_receipt_accepts_string_ids_when_customer_matches_order(self):
        order = self._create_order(code='DH-RECEIPT-STRING-IDS')

        response = self.client.post(
            reverse('api_save_receipt'),
            data=json.dumps({
                'code': 'PT-STRING-IDS',
                'order_id': str(order.id),
                'customer_id': str(self.customer.id),
                'amount': 100,
                'receipt_date': date.today().isoformat(),
                'status': 0,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())
        receipt = Receipt.objects.get(code='PT-STRING-IDS')
        self.assertEqual(receipt.order_id, order.id)
        self.assertEqual(receipt.customer_id, self.customer.id)
        self.assertEqual(receipt.store_id, self.store.id)

    def test_save_payment_assigns_store_from_goods_receipt(self):
        goods_receipt = self._create_goods_receipt(code='PN-001')
        cash_book = CashBook.objects.create(name='Quỹ B', balance=Decimal('1000'))

        response = self.client.post(
            reverse('api_save_payment'),
            data=json.dumps({
                'code': 'PC-STORE-001',
                'goods_receipt_id': goods_receipt.id,
                'cash_book_id': cash_book.id,
                'amount': 100,
                'payment_date': date.today().isoformat(),
                'status': 0,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')

        payment = Payment.objects.get(code='PC-STORE-001')
        self.assertEqual(payment.store_id, self.store.id)
        self.assertEqual(payment.goods_receipt_id, goods_receipt.id)

    def test_regular_staff_cannot_save_cashbook(self):
        response = self.client.post(
            reverse('api_save_cashbook'),
            data=json.dumps({
                'name': 'Quỹ staff',
                'description': 'Không được tạo',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['status'], 'error')
