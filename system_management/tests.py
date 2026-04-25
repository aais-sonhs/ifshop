import importlib
import json
import sys

from django.contrib.auth.models import User
from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from system_management.models import Brand, BusinessConfig, PrinterSetting, RoleGroup, Store, UserProfile


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

    def test_save_brand_forces_owner_to_current_brand_owner(self):
        response = self.client.post(
            reverse('api_save_brand'),
            data=json.dumps({
                'name': 'Brand Owner Created',
                'owner_id': self.other_owner.id,
                'business_type': 'retail',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok', msg=response.content.decode())

        brand = Brand.objects.get(name='Brand Owner Created')
        self.assertEqual(brand.owner_id, self.owner.id)

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

    def test_brand_owner_cannot_create_global_role_group(self):
        response = self.client.post(
            reverse('api_save_role_group'),
            data=json.dumps({'name': 'Owner Global Role'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(RoleGroup.objects.filter(name='Owner Global Role').exists())

    def test_regular_staff_cannot_read_printer_settings(self):
        PrinterSetting.objects.create(name='LAN Printer', printer_type='lan', ip_address='192.168.1.10')
        self.client.force_login(self.staff_a)

        response = self.client.get(reverse('api_get_printers'))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['status'], 'error')

    def test_superadmin_can_open_platform_management_routes(self):
        self.client.force_login(self.superuser)

        for route_name in ('brand_tbl', 'user_management_tbl', 'role_group_tbl', 'permission_tbl'):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200, msg=route_name)

        api_response = self.client.get(reverse('api_get_role_groups'))
        self.assertEqual(api_response.status_code, 200)
        self.assertIn('data', api_response.json())

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
