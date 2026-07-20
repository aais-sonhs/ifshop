import os
from io import StringIO
from tempfile import NamedTemporaryFile

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from openpyxl import Workbook

from customers.management.commands.import_customers_excel import EXPECTED_HEADERS
from customers.models import Customer, CustomerAddress, CustomerGroup
from system_management.models import Brand, Store, UserProfile


class ImportCustomersExcelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name='Import Customer Brand')
        cls.store = Store.objects.create(
            brand=cls.brand,
            code='IMPORT-STORE',
            name='Import Customer Store',
        )
        cls.user = User.objects.create_user(username='customer_importer', password='pass123')
        UserProfile.objects.create(user=cls.user, store=cls.store)
        cls.retail_group = CustomerGroup.objects.create(code='BANLE', name='Bán lẻ')
        cls.wholesale_group = CustomerGroup.objects.create(code='BANBUON', name='Bán buôn')

    def setUp(self):
        self.existing_customer = Customer.objects.create(
            store=self.store,
            created_by=self.user,
            code='CUS-EXISTING',
            name='Khách hiện có',
            phone='0901000000',
            address='Địa chỉ đã chỉnh trong hệ thống',
            group=self.retail_group,
        )
        CustomerAddress.objects.create(
            customer=self.existing_customer,
            label='Địa chỉ thủ công',
            address='Kho đang dùng',
            phone='0901000001',
        )

    def _build_excel_file(self):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(EXPECTED_HEADERS)
        worksheet.append([
            'Khách hiện có', 'CUS-EXISTING', 'BANLE', '0901000000', 'Nam',
            '12 Phố trong file', 'Hà Nội', 'Quận Hoàn Kiếm', 'Phường Hàng Bạc',
            5, 12, 1, '17/07/2026 10:30', '0901000099', '',
        ])
        worksheet.append([
            '', '', '', '', '', 'Điểm nhận thứ hai', 'Hà Nội',
            'Quận Ba Đình', 'Phường Trúc Bạch', 0, 0, 0, '', '0901000002', '',
        ])
        worksheet.append([
            'Khách mới', 'CUS-NEW', 'BANBUON', '0988000000', 'Nữ',
            '25 Đường mới', 'Hải Phòng', 'Quận Hồng Bàng', 'Phường Sở Dầu',
            2, 7, 0, '16/07/2026 08:15', '0988000000', '0988111111',
        ])
        worksheet.append([
            '', '', '', '', '', 'Kho khách mới', 'Hải Phòng',
            'Quận Lê Chân', 'Phường An Biên', 0, 0, 0, '', '0988222222', '',
        ])

        temp_file = NamedTemporaryFile(suffix='.xlsx', delete=False)
        temp_file.close()
        workbook.save(temp_file.name)
        self.addCleanup(lambda: os.path.exists(temp_file.name) and os.unlink(temp_file.name))
        return temp_file.name

    def _run_import(self, excel_file, apply=False):
        output = StringIO()
        args = [
            excel_file,
            '--store-id', str(self.store.id),
            '--user-id', str(self.user.id),
        ]
        if apply:
            args.append('--apply')
        call_command('import_customers_excel', *args, stdout=output)
        return output.getvalue()

    def test_dry_run_does_not_write_data(self):
        excel_file = self._build_excel_file()

        output = self._run_import(excel_file)

        self.assertIn('CHẠY THỬ - CHƯA GHI DỮ LIỆU', output)
        self.assertFalse(Customer.objects.filter(code='CUS-NEW').exists())
        self.assertEqual(CustomerAddress.objects.count(), 1)

    def test_apply_merges_addresses_without_overwriting_existing_main_address(self):
        excel_file = self._build_excel_file()

        output = self._run_import(excel_file, apply=True)

        self.assertIn('ĐÃ GHI DỮ LIỆU', output)
        self.existing_customer.refresh_from_db()
        self.assertEqual(self.existing_customer.address, 'Địa chỉ đã chỉnh trong hệ thống')
        self.assertEqual(self.existing_customer.province or '', '')

        existing_addresses = list(
            self.existing_customer.delivery_addresses.order_by('sort_order').values_list(
                'label', 'address', 'phone'
            )
        )
        self.assertEqual(existing_addresses[0], ('Địa chỉ thủ công', 'Kho đang dùng', '0901000001'))
        self.assertIn(
            (
                'Địa chỉ chính từ Excel',
                '12 Phố trong file, Phường Hàng Bạc, Quận Hoàn Kiếm, Hà Nội',
                '0901000099',
            ),
            existing_addresses,
        )
        self.assertIn(
            (
                'Địa chỉ phụ từ Excel 2',
                'Điểm nhận thứ hai, Phường Trúc Bạch, Quận Ba Đình, Hà Nội',
                '0901000002',
            ),
            existing_addresses,
        )

        new_customer = Customer.objects.get(code='CUS-NEW')
        self.assertEqual(new_customer.store, self.store)
        self.assertEqual(new_customer.created_by, self.user)
        self.assertEqual(new_customer.address, '25 Đường mới')
        self.assertEqual(new_customer.province, 'Hải Phòng')
        self.assertEqual(new_customer.group, self.wholesale_group)
        self.assertEqual(new_customer.customer_kind, Customer.CUSTOMER_KIND_WHOLESALE)
        self.assertEqual(new_customer.gender, 2)
        self.assertEqual(new_customer.order_count, 2)
        self.assertTrue(new_customer.imported_legacy_metrics)
        self.assertEqual(
            list(new_customer.delivery_addresses.values_list('address', 'phone')),
            [('Kho khách mới, Phường An Biên, Quận Lê Chân, Hải Phòng', '0988222222')],
        )

        customer_count = Customer.objects.count()
        address_count = CustomerAddress.objects.count()
        self._run_import(excel_file, apply=True)
        self.assertEqual(Customer.objects.count(), customer_count)
        self.assertEqual(CustomerAddress.objects.count(), address_count)
