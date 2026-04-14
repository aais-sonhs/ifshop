import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from system_management.models import Brand, Store, UserProfile


class SystemManagementScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='brand_owner_a', password='pass123')
        cls.other_owner = User.objects.create_user(username='brand_owner_b', password='pass123')
        cls.staff_a = User.objects.create_user(username='staff_a', password='pass123')
        cls.staff_b = User.objects.create_user(username='staff_b', password='pass123')

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
