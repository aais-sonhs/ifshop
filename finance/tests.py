import json
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from customers.models import Customer
from finance.models import CashBook, Payment, PaymentMethodOption, Receipt
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

    def test_payment_list_returns_paginated_meta_when_requested(self):
        today = date.today()
        for index in range(11):
            Payment.objects.create(
                code=f'PC-PAGE-{index:02d}',
                store=self.store,
                amount=Decimal('100'),
                payment_date=today - timedelta(days=10 - index),
                status=1,
                created_by=self.user,
            )

        response = self.client.get(
            reverse('api_get_payments'),
            data={'page': 2, 'page_size': 10},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['meta']['page'], 2)
        self.assertEqual(payload['meta']['page_size'], 10)
        self.assertEqual(payload['meta']['page_count'], 1)
        self.assertEqual(payload['meta']['total_pages'], 2)
        self.assertEqual(payload['meta']['total_filtered_count'], 11)
        self.assertEqual(payload['meta']['start_index'], 11)
        self.assertEqual(payload['meta']['end_index'], 11)
        self.assertFalse(payload['meta']['has_next'])
        self.assertEqual([item['code'] for item in payload['data']], ['PC-PAGE-00'])
        self.assertEqual(payload['meta']['next_code'], 'PC-001')

    def test_payment_list_without_pagination_keeps_legacy_full_response(self):
        for index in range(11):
            Payment.objects.create(
                code=f'PC-LEGACY-{index:02d}',
                store=self.store,
                amount=Decimal('100'),
                payment_date=date.today() - timedelta(days=index),
                status=1,
                created_by=self.user,
            )

        response = self.client.get(reverse('api_get_payments'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn('meta', payload)
        self.assertEqual(len(payload['data']), 11)
        self.assertEqual(payload['next_code'], 'PC-001')

    def test_save_payment_auto_generates_code_when_blank(self):
        response = self.client.post(
            reverse('api_save_payment'),
            data=json.dumps({
                'code': '',
                'amount': 100,
                'payment_date': date.today().isoformat(),
                'status': 0,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())
        payment = Payment.objects.get(amount=Decimal('100'))
        self.assertEqual(payment.code, 'PC-001')
        self.assertEqual(payment.store_id, self.store.id)

    def test_finance_entries_api_returns_paginated_combined_rows(self):
        today = date.today()
        for index in range(6):
            Receipt.objects.create(
                code=f'PT-LIST-{index:02d}',
                store=self.store,
                customer=self.customer,
                amount=Decimal('100'),
                receipt_date=today - timedelta(days=index),
                status=1,
                created_by=self.user,
            )
        for index in range(5):
            Payment.objects.create(
                code=f'PC-LIST-{index:02d}',
                store=self.store,
                amount=Decimal('50'),
                payment_date=today - timedelta(days=index + 6),
                status=1,
                created_by=self.user,
            )

        response = self.client.get(
            reverse('api_get_finance_entries'),
            data={'page': 2, 'page_size': 10},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['meta']['page'], 2)
        self.assertEqual(payload['meta']['page_size'], 10)
        self.assertEqual(payload['meta']['page_count'], 1)
        self.assertEqual(payload['meta']['total_pages'], 2)
        self.assertEqual(payload['meta']['total_filtered_count'], 11)
        self.assertEqual(payload['meta']['start_index'], 11)
        self.assertEqual(payload['meta']['end_index'], 11)
        self.assertFalse(payload['meta']['has_next'])
        self.assertEqual(payload['data'][0]['code'], 'PC-LIST-04')
        self.assertEqual(payload['data'][0]['type'], 'Chi')
        self.assertEqual(payload['data'][0]['status_display'], 'Hoàn thành')

    def test_finance_entries_api_filters_by_type(self):
        Receipt.objects.create(
            code='PT-FILTER-001',
            store=self.store,
            customer=self.customer,
            amount=Decimal('100'),
            receipt_date=date.today(),
            status=1,
            created_by=self.user,
        )
        Payment.objects.create(
            code='PC-FILTER-001',
            store=self.store,
            amount=Decimal('50'),
            payment_date=date.today(),
            status=1,
            created_by=self.user,
        )

        response = self.client.get(
            reverse('api_get_finance_entries'),
            data={'type': 'thu', 'page': 1, 'page_size': 10},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['meta']['total_filtered_count'], 1)
        self.assertEqual([item['code'] for item in payload['data']], ['PT-FILTER-001'])
        self.assertEqual(payload['data'][0]['type'], 'Thu')

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

    def test_save_receipt_cannot_change_linked_order_when_editing(self):
        original_order = self._create_order(code='DH-RECEIPT-LOCKED-1')
        other_order = self._create_order(code='DH-RECEIPT-LOCKED-2')
        receipt = Receipt.objects.create(
            code='PT-LOCKED-ORDER',
            store=self.store,
            customer=self.customer,
            order=original_order,
            amount=Decimal('50'),
            receipt_date=date.today(),
            status=0,
            created_by=self.user,
        )

        response = self.client.post(
            reverse('api_save_receipt'),
            data=json.dumps({
                'id': receipt.id,
                'code': receipt.code,
                'category_id': None,
                'customer_id': self.customer.id,
                'order_id': other_order.id,
                'amount': 60,
                'receipt_date': date.today().isoformat(),
                'status': 0,
                'description': 'Thu thêm',
                'note': 'Không được đổi đơn',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('đơn hàng', payload['message'].lower())

        receipt.refresh_from_db()
        self.assertEqual(receipt.order_id, original_order.id)
        self.assertEqual(receipt.amount, Decimal('50'))

    def test_delete_receipt_endpoint_rejects_deletion(self):
        receipt = Receipt.objects.create(
            code='PT-NO-DELETE',
            store=self.store,
            customer=self.customer,
            amount=Decimal('50'),
            receipt_date=date.today(),
            status=0,
            created_by=self.user,
        )

        response = self.client.post(
            reverse('api_delete_receipt'),
            data=json.dumps({'id': receipt.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('không được xóa', payload['message'].lower())
        self.assertTrue(Receipt.objects.filter(id=receipt.id).exists())

    def test_save_receipt_partial_edit_preserves_fixed_and_payment_fields(self):
        order = self._create_order(code='DH-RECEIPT-PARTIAL-EDIT')
        cash_book = CashBook.objects.create(name='Quỹ giữ nguyên', balance=Decimal('1000'))
        receipt = Receipt.objects.create(
            code='PT-PARTIAL-EDIT',
            store=self.store,
            customer=self.customer,
            order=order,
            cash_book=cash_book,
            amount=Decimal('75'),
            receipt_date=date.today(),
            status=0,
            payment_method=1,
            created_by=self.user,
        )

        response = self.client.post(
            reverse('api_save_receipt'),
            data=json.dumps({
                'id': receipt.id,
                'description': 'Chỉ sửa diễn giải',
                'note': 'Giữ nguyên đơn và hình thức thanh toán',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())

        receipt.refresh_from_db()
        self.assertEqual(receipt.order_id, order.id)
        self.assertEqual(receipt.customer_id, self.customer.id)
        self.assertEqual(receipt.cash_book_id, cash_book.id)
        self.assertEqual(receipt.amount, Decimal('75'))
        self.assertEqual(receipt.payment_method, 1)
        self.assertEqual(receipt.description, 'Chỉ sửa diễn giải')
        self.assertEqual(receipt.note, 'Giữ nguyên đơn và hình thức thanh toán')

    def test_export_receipts_excel_includes_note_column(self):
        Receipt.objects.create(
            code='PT-EXPORT-NOTE',
            store=self.store,
            customer=self.customer,
            amount=Decimal('125000'),
            receipt_date=date.today(),
            status=1,
            description='Thu tiền đơn test',
            note='Ghi chú cần xuất Excel',
            created_by=self.user,
        )

        response = self.client.get(reverse('export_receipts_excel'))

        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook.active
        headers = [cell.value for cell in worksheet[4]]
        self.assertIn('Ghi chú', headers)
        note_index = headers.index('Ghi chú') + 1
        self.assertEqual(worksheet.cell(row=5, column=note_index).value, 'Ghi chú cần xuất Excel')

    def test_brand_owner_can_create_payment_method_option(self):
        owner = User.objects.create_user(username='finance_owner', password='pass123')
        self.brand.owner = owner
        self.brand.save(update_fields=['owner'])
        cash_book = CashBook.objects.create(name='Tài khoản MoMo', balance=Decimal('0'))
        self.client.force_login(owner)

        response = self.client.post(
            reverse('api_save_payment_method'),
            data=json.dumps({
                'code': 'momo_test',
                'name': 'Ví MoMo test',
                'legacy_type': 3,
                'default_cash_book_id': cash_book.id,
                'sort_order': 10,
                'is_active': True,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok', msg=response.content.decode())
        method = PaymentMethodOption.objects.get(code='MOMO_TEST')
        self.assertEqual(payload['method']['id'], method.id)
        self.assertEqual(method.default_cash_book_id, cash_book.id)

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

    def test_cashbook_page_hides_create_button_for_regular_staff(self):
        response = self.client.get(reverse('cashbook_tbl'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="btn_add_cashbook"')
        self.assertNotContains(response, 'id="modal_cashbook"')

    def test_cashbook_page_shows_create_button_to_brand_owner(self):
        self.brand.owner = self.user
        self.brand.save(update_fields=['owner'])

        response = self.client.get(reverse('cashbook_tbl'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="btn_add_cashbook"')
        self.assertContains(response, 'id="modal_cashbook"')
