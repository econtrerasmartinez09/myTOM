from django.test import TestCase
from django.urls import reverse

from faker import Faker

class MyViewTestCase(TestCase):

    def setUpTestData(cls):



        pass

    def setUp(self):

        pass

    def tearDown(self):

        pass

    def test_my_view_pass(self):
        response = self.client.get(reverse('my-view'))
        self.assertEqual(response.status_code, 200)

        self.assertFalse(False)

    def test_my_view_fail(self):

        self.assertTrue(False)