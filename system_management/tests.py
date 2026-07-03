import importlib
import json
import sys

from django.contrib.auth.models import User
from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.store_utils import can_access_module
from system_management.models import (
    Brand, BusinessConfig, PrinterSetting, PrintTemplate, PrintTemplateHistory,
    RoleGroup, Store, UserProfile,
)


class StaticFileRoutingTests(SimpleTestCase):
    @override_settings(DEBUG=True)
    def test_debug_static_routes_use_staticfiles_finders(self):
        import config as config_package

        original_module = sys.modules.pop('config.urls', None)
        had_original_attr = hasattr(config_package, 'urls')
        original_attr = getattr(config_package, 'urls', None)
        try:
            urls = importlib.import_module('config.urls')

            def pattern_regex(pattern):
                return getattr(pattern.pattern, '_regex', str(pattern.pattern))

            static_patterns = [
                pattern for pattern in urls.urlpatterns
                if pattern_regex(pattern) == r'^static/(?P<path>.*)$'
            ]
            self.assertEqual(len(static_patterns), 1)
            self.assertIs(static_patterns[0].callback, staticfiles_serve)

            root_static_patterns = {
                pattern_regex(pattern): pattern for pattern in urls.urlpatterns
                if pattern_regex(pattern) in {r'^sw\.js$', r'^manifest\.json$'}
            }
            self.assertEqual(set(root_static_patterns), {r'^sw\.js$', r'^manifest\.json$'})
            for pattern in root_static_patterns.values():
                self.assertIs(pattern.callback, staticfiles_serve)
        finally:
            if original_module is None:
                sys.modules.pop('config.urls', None)
            else:
                sys.modules['config.urls'] = original_module

            if had_original_attr:
                setattr(config_package, 'urls', original_attr)
            elif hasattr(config_package, 'urls'):
                delattr(config_package, 'urls')


class SystemManagementScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='brand_owner_a', password='pass123')
        cls.other_owner = User.objects.create_user(username='brand_owner_b', password='pass123')
        cls.staff_a = User.objects.create_user(username='staff_a', password='pass123')
        cls.staff_b = User.objects.create_user(username='staff_b', password='pass123')
        cls.superuser = User.objects.create_superuser(
            username='platform_admin',
            password='pass123',
            email='admin@example.com',
        )

        cls.brand = Brand.objects.create(name='Brand A', owner=cls.owner)
        cls.other_brand = Brand.objects.create(name='Brand B', owner=cls.other_owner)

        cls.store = Store.objects.create(brand=cls.brand, name='Store A', code='SMA')
        cls.other_store = Store.objects.create(brand=cls.other_brand, name='Store B', code='SMB')

        UserProfile.objects.create(user=cls.staff_a, store=cls.store)
        UserProfile.objects.create(user=cls.staff_b, store=cls.other_store)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_save_user_rejects_foreign_store_user(self):
        response = self.client.post(
            reverse('api_save_user'),
            data=json.dumps({
                'id': self.staff_b.id,
                'first_name': 'Changed',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['message'], 'Bạn không có quyền chỉnh sửa người dùng này')

    def test_save_user_rejects_other_brand_owner_without_profile(self):
        old_password = self.other_owner.password

        response = self.client.post(
            reverse('api_save_user'),
            data=json.dumps({
                'id': self.other_owner.id,
                'first_name': 'Hijacked',
                'password': 'newpass123',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['message'], 'Bạn không có quyền chỉnh sửa người dùng này')

        self.other_owner.refresh_from_db()
        self.assertEqual(self.other_owner.first_name, '')
        self.assertEqual(self.other_owner.password, old_password)
        self.assertFalse(UserProfile.objects.filter(user=self.other_owner).exists())

    def test_brand_owner_user_list_excludes_other_brand_owner_without_profile(self):
        response = self.client.get(reverse('api_get_users'))

        self.assertEqual(response.status_code, 200)
        user_ids = {row['id'] for row in response.json()['data']}
        self.assertIn(self.owner.id, user_ids)
        self.assertIn(self.staff_a.id, user_ids)
        self.assertNotIn(self.other_owner.id, user_ids)

    def test_brand_owner_brand_user_dropdown_excludes_other_owner_without_profile(self):
        response = self.client.get(reverse('api_get_brands'))

        self.assertEqual(response.status_code, 200)
        user_ids = {row['id'] for row in response.json()['users']}
        self.assertIn(self.owner.id, user_ids)
        self.assertIn(self.staff_a.id, user_ids)
        self.assertNotIn(self.other_owner.id, user_ids)

    def test_save_store_rejects_foreign_brand(self):
        response = self.client.post(
            reverse('api_save_store'),
            data=json.dumps({
                'brand_id': self.other_brand.id,
                'code': 'NEW1',
                'name': 'Foreign Store',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['message'], 'Thương hiệu không thuộc phạm vi quản lý của bạn')

    def test_delete_store_rejects_foreign_store(self):
        response = self.client.post(
            reverse('api_delete_store'),
            data=json.dumps({'id': self.other_store.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['message'], 'Không tìm thấy cửa hàng')

    def test_superadmin_can_create_brand_for_specific_owner(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse('api_save_brand'),
            data=json.dumps({
                'name': 'Superadmin Created Brand',
                'owner_id': self.other_owner.id,
                'business_type': 'retail',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())

        brand = Brand.objects.get(name='Superadmin Created Brand')
        self.assertEqual(brand.owner_id, self.other_owner.id)

    def test_brand_owner_cannot_create_brand(self):
        response = self.client.post(
            reverse('api_save_brand'),
            data=json.dumps({
                'name': 'Brand Owner Created',
                'owner_id': self.other_owner.id,
                'business_type': 'retail',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Brand.objects.filter(name='Brand Owner Created').exists())

    def test_brand_owner_cannot_delete_brand(self):
        response = self.client.post(
            reverse('api_delete_brand'),
            data=json.dumps({'id': self.brand.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Brand.objects.filter(id=self.brand.id).exists())

    def test_regular_staff_cannot_create_brand(self):
        self.client.force_login(self.staff_a)

        response = self.client.post(
            reverse('api_save_brand'),
            data=json.dumps({
                'name': 'Staff Created Brand',
                'business_type': 'retail',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Brand.objects.filter(name='Staff Created Brand').exists())

    def test_regular_staff_cannot_create_role_group(self):
        self.client.force_login(self.staff_a)

        response = self.client.post(
            reverse('api_save_role_group'),
            data=json.dumps({'name': 'Staff Role'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)

    def test_brand_owner_can_create_brand_role_group(self):
        response = self.client.post(
            reverse('api_save_role_group'),
            data=json.dumps({'name': 'Owner Global Role'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())
        self.assertTrue(RoleGroup.objects.filter(brand=self.brand, name='Owner Global Role').exists())

    def test_brand_owner_can_assign_role_group_when_saving_managed_user(self):
        groups_response = self.client.get(reverse('api_get_role_groups'))
        self.assertEqual(groups_response.status_code, 200)
        role_group_row = next(row for row in groups_response.json()['data'] if row['name'] == 'Kế toán')
        role_group = RoleGroup.objects.get(id=role_group_row['id'])
        self.assertIn(role_group.id, {row['id'] for row in groups_response.json()['data']})

        response = self.client.post(
            reverse('api_save_user'),
            data=json.dumps({
                'id': self.staff_a.id,
                'first_name': 'Staff',
                'last_name': 'A',
                'email': 'staff-a@example.com',
                'store_id': self.store.id,
                'position': 'Kế toán',
                'is_active': True,
                'group_ids': [role_group.id],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())
        self.assertTrue(self.staff_a.groups.filter(id=role_group.group_id).exists())

        list_response = self.client.get(reverse('api_get_users'))
        row = next(item for item in list_response.json()['data'] if item['id'] == self.staff_a.id)
        self.assertEqual(row['group_ids'], [role_group.id])
        self.assertEqual(row['position'], 'Kế toán')

    def test_password_only_update_preserves_user_profile_and_groups(self):
        groups_response = self.client.get(reverse('api_get_role_groups'))
        role_group_row = next(row for row in groups_response.json()['data'] if row['name'] == 'Nhân viên bán hàng')
        role_group = RoleGroup.objects.get(id=role_group_row['id'])
        self.staff_a.groups.add(role_group.group)
        self.staff_a.profile.position = 'Nhân viên bán hàng'
        self.staff_a.profile.save(update_fields=['position'])

        response = self.client.post(
            reverse('api_save_user'),
            data=json.dumps({
                'id': self.staff_a.id,
                'password': 'newpass123',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())
        self.staff_a.refresh_from_db()
        self.staff_a.profile.refresh_from_db()
        self.assertEqual(self.staff_a.profile.store_id, self.store.id)
        self.assertEqual(self.staff_a.profile.position, 'Nhân viên bán hàng')
        self.assertTrue(self.staff_a.groups.filter(id=role_group.group_id).exists())
        self.assertTrue(self.staff_a.check_password('newpass123'))

    def test_brand_owner_can_manage_permission_matrix_for_brand_role_group(self):
        response = self.client.get(reverse('permission_tbl'))
        self.assertEqual(response.status_code, 200)

        groups_response = self.client.get(reverse('api_get_role_groups'))
        self.assertEqual(groups_response.status_code, 200)
        role_group_row = next(row for row in groups_response.json()['data'] if row['name'] == 'Kế toán')
        role_group = RoleGroup.objects.get(id=role_group_row['id'])

        permission_response = self.client.get(
            reverse('api_get_role_group_permissions'),
            {'role_group_id': role_group.id},
        )
        self.assertEqual(permission_response.status_code, 200)
        permission_payload = permission_response.json()
        self.assertEqual(permission_payload['status'], 'ok')
        self.assertTrue(permission_payload['permissions']['reports']['view'])
        self.assertFalse(permission_payload['permissions']['orders']['add'])

        permission_map = permission_payload['permissions']
        permission_map['orders']['add'] = True
        permission_map['reports']['view'] = False
        save_response = self.client.post(
            reverse('api_save_role_group_permissions'),
            data=json.dumps({
                'role_group_id': role_group.id,
                'permissions': permission_map,
            }),
            content_type='application/json',
        )
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.json()['status'], 'ok', msg=save_response.content.decode())

        reload_response = self.client.get(
            reverse('api_get_role_group_permissions'),
            {'role_group_id': role_group.id},
        )
        self.assertEqual(reload_response.status_code, 200)
        reloaded = reload_response.json()['permissions']
        self.assertTrue(reloaded['orders']['add'])
        self.assertFalse(reloaded['reports']['view'])

        self.staff_a.groups.set([role_group.group])
        self.assertTrue(can_access_module(self.staff_a, 'orders', 'add'))
        self.assertFalse(can_access_module(self.staff_a, 'reports', 'view'))

    def test_regular_staff_can_read_active_printers_for_print_preview(self):
        PrinterSetting.objects.create(name='LAN Printer', printer_type='lan', ip_address='192.168.1.10')
        self.client.force_login(self.staff_a)

        response = self.client.get(reverse('api_get_printers'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'][0]['name'], 'LAN Printer')

    def test_regular_staff_can_read_printers_by_selected_brand(self):
        sibling_brand = Brand.objects.create(name='Z Brand Child', owner=self.owner)
        PrinterSetting.objects.create(
            brand=self.brand,
            name='Brand A Printer',
            printer_type='lan',
            ip_address='192.168.1.10',
        )
        PrinterSetting.objects.create(
            brand=sibling_brand,
            name='Brand Child Printer',
            printer_type='lan',
            ip_address='192.168.1.11',
        )
        PrinterSetting.objects.create(
            name='Global Printer',
            printer_type='lan',
            ip_address='192.168.1.12',
        )
        self.client.force_login(self.staff_a)

        response = self.client.get(reverse('api_get_printers'), {'brand_id': sibling_brand.id})

        self.assertEqual(response.status_code, 200)
        names = {row['name'] for row in response.json()['data']}
        self.assertIn('Brand Child Printer', names)
        self.assertIn('Global Printer', names)
        self.assertNotIn('Brand A Printer', names)

    def test_save_print_template_supports_explicit_brand_selection(self):
        sibling_brand = Brand.objects.create(name='Z Brand Template', owner=self.owner)
        payload = {
            'brand_id': sibling_brand.id,
            'template_type': 'a4',
            'title': 'Hoa don cong ty con',
            'header_note': '',
            'terms': '',
            'footer_note': '',
            'show_brand_logo': True,
            'show_brand_info': True,
            'show_customer_info': True,
            'show_signatures': True,
            'show_product_images': False,
            'show_product_code': True,
            'show_unit_price': True,
            'show_discount': True,
            'show_tax': True,
            'show_shipping_fee': True,
            'show_payment_info': True,
            'show_order_note': True,
            'show_item_note': False,
            'show_terms': True,
            'show_print_time': True,
            'show_combo_components': True,
        }

        response = self.client.post(
            reverse('api_save_print_template'),
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())
        template = PrintTemplate.objects.get(brand=sibling_brand, template_type='a4')
        self.assertEqual(template.title, 'Hoa don cong ty con')

    def test_save_print_template_creates_history_and_restores_snapshot(self):
        payload = {
            'template_type': 'a4',
            'title': 'Hóa đơn tùy chỉnh',
            'header_note': 'Ghi chú đầu',
            'terms': 'Điều khoản',
            'footer_note': 'Cảm ơn',
            'show_brand_logo': True,
            'show_brand_info': True,
            'show_customer_info': True,
            'show_signatures': True,
            'show_product_images': True,
            'show_product_code': True,
            'show_unit_price': True,
            'show_discount': False,
            'show_tax': True,
            'show_shipping_fee': True,
            'show_payment_info': True,
            'show_order_note': True,
            'show_item_note': True,
            'show_terms': True,
            'show_print_time': False,
            'show_combo_components': False,
        }

        response = self.client.post(
            reverse('api_save_print_template'),
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())
        template = PrintTemplate.objects.get(brand=self.brand, template_type='a4')
        self.assertFalse(template.show_discount)
        self.assertFalse(template.show_print_time)
        self.assertFalse(template.show_combo_components)
        history = PrintTemplateHistory.objects.get(template=template)
        self.assertTrue(history.snapshot['show_product_images'])
        self.assertFalse(history.snapshot['show_print_time'])
        self.assertFalse(history.snapshot['show_combo_components'])

        template.show_discount = True
        template.show_product_images = False
        template.show_print_time = True
        template.show_combo_components = True
        template.save()
        restore = self.client.post(
            reverse('api_restore_print_template_history'),
            data=json.dumps({'history_id': history.id}),
            content_type='application/json',
        )

        self.assertEqual(restore.status_code, 200)
        self.assertEqual(restore.json()['status'], 'ok', msg=restore.content.decode())
        template.refresh_from_db()
        self.assertFalse(template.show_discount)
        self.assertTrue(template.show_product_images)
        self.assertFalse(template.show_print_time)
        self.assertFalse(template.show_combo_components)
        self.assertEqual(template.histories.count(), 2)

    def test_preview_print_template_uses_unsaved_options(self):
        payload = {
            'template_type': 'a4',
            'title': 'Hóa đơn preview',
            'header_note': '',
            'terms': '',
            'footer_note': '',
            'show_brand_logo': True,
            'show_brand_info': True,
            'show_customer_info': True,
            'show_signatures': False,
            'show_product_images': True,
            'show_product_code': True,
            'show_unit_price': True,
            'show_discount': False,
            'show_tax': True,
            'show_shipping_fee': True,
            'show_payment_info': True,
            'show_order_note': True,
            'show_item_note': True,
            'show_terms': True,
            'show_print_time': True,
            'show_combo_components': True,
        }

        response = self.client.post(
            reverse('api_preview_print_template'),
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'ok', msg=response.content.decode())
        self.assertIn('Hóa đơn preview', body['html'])
        self.assertIn('Không ảnh', body['html'])
        self.assertIn('SP001 - Áo khoác mẫu', body['html'])
        self.assertNotIn('CK%', body['html'])

    def test_preview_print_template_can_hide_combo_components(self):
        payload = {
            'template_type': 'a4',
            'title': 'Hóa đơn không hiện combo',
            'header_note': '',
            'terms': '',
            'footer_note': '',
            'show_brand_logo': True,
            'show_brand_info': True,
            'show_customer_info': True,
            'show_signatures': True,
            'show_product_images': False,
            'show_product_code': True,
            'show_unit_price': True,
            'show_discount': True,
            'show_tax': True,
            'show_shipping_fee': True,
            'show_payment_info': True,
            'show_order_note': True,
            'show_item_note': False,
            'show_terms': True,
            'show_print_time': True,
            'show_combo_components': False,
        }

        response = self.client.post(
            reverse('api_preview_print_template'),
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'ok', msg=response.content.decode())
        self.assertIn('Combo mẫu', body['html'])
        self.assertNotIn('SP001 - Áo khoác mẫu', body['html'])

    def test_preview_print_template_can_hide_export_print_time(self):
        payload = {
            'template_type': 'export',
            'title': 'Phiếu xuất kho preview',
            'header_note': '',
            'terms': '',
            'footer_note': '',
            'show_brand_logo': True,
            'show_brand_info': True,
            'show_customer_info': True,
            'show_signatures': True,
            'show_product_images': False,
            'show_product_code': True,
            'show_unit_price': True,
            'show_discount': True,
            'show_tax': True,
            'show_shipping_fee': True,
            'show_payment_info': True,
            'show_order_note': True,
            'show_item_note': False,
            'show_terms': True,
            'show_print_time': False,
            'show_combo_components': True,
        }

        response = self.client.post(
            reverse('api_preview_print_template'),
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'ok', msg=response.content.decode())
        self.assertIn('Phiếu xuất kho preview', body['html'])
        self.assertNotIn('Ngày in:', body['html'])

    def test_superadmin_can_open_platform_management_routes(self):
        self.client.force_login(self.superuser)

        for route_name in ('brand_tbl', 'user_management_tbl', 'service_price_tbl'):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200, msg=route_name)

        api_response = self.client.get(reverse('api_get_role_groups'))
        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.json()['data'], [])

        service_price_response = self.client.get(reverse('api_get_service_prices'))
        self.assertEqual(service_price_response.status_code, 200)

    def test_superadmin_is_redirected_from_brand_owned_system_settings(self):
        self.client.force_login(self.superuser)

        for route_name in ('role_group_tbl', 'permission_tbl', 'category_tbl', 'printer_setting_tbl', 'print_template_setting'):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 302, msg=route_name)
            self.assertEqual(response.url, '/brand-tbl/')

        for route_name in ('api_get_role_group_permissions', 'api_get_printers', 'api_get_print_templates'):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 403, msg=route_name)

    def test_superadmin_is_blocked_from_shop_operation_apis(self):
        PrinterSetting.objects.create(name='LAN Printer', printer_type='lan', ip_address='192.168.1.10')
        self.client.force_login(self.superuser)

        for route_name in ('api_get_business_config',):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 403, msg=route_name)

    def test_superadmin_cannot_open_brand_owner_configuration_routes(self):
        self.client.force_login(self.superuser)

        for route_name in ('business_config_tbl', 'print_template_setting'):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 302, msg=route_name)
            self.assertEqual(response['Location'], '/brand-tbl/')

    def test_product_guide_is_available_for_owner_and_superadmin(self):
        response = self.client.get(reverse('product_guide'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tài liệu hướng dẫn')
        self.assertNotContains(response, 'abcd@1234')

        self.client.force_login(self.superuser)
        super_response = self.client.get(reverse('product_guide'))
        self.assertEqual(super_response.status_code, 200)
        self.assertContains(super_response, 'Tài liệu hướng dẫn')

    def test_business_config_exposes_and_saves_negative_stock_option(self):
        response = self.client.get(reverse('api_get_business_config'))
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertIn('opt_allow_negative_stock', data)

        data['opt_allow_negative_stock'] = True
        save_response = self.client.post(
            reverse('api_save_business_config'),
            data=json.dumps(data),
            content_type='application/json',
        )

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.json()['status'], 'ok', msg=save_response.content.decode())
        config = BusinessConfig.get_config(brand=self.brand)
        self.assertTrue(config.opt_allow_negative_stock)
