import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from spa.models import Service
from system_management.models import Brand, Store, UserProfile


class SpaPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name='Spa Permission Brand')
        cls.store = Store.objects.create(brand=cls.brand, name='Spa Store', code='SPA')
        cls.user = User.objects.create_user(username='spa_staff', password='pass123')
        UserProfile.objects.create(user=cls.user, store=cls.store)

    def setUp(self):
        self.client.force_login(self.user)

    def test_regular_staff_cannot_save_spa_service(self):
        response = self.client.post(
            reverse('api_spa_services_save'),
            data=json.dumps({
                'code': 'DV-STAFF',
                'name': 'Dịch vụ staff',
                'price': 100,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['status'], 'error')
        self.assertFalse(Service.objects.filter(code='DV-STAFF').exists())
