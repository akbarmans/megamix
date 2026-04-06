"""
Базовые тесты для shop-приложения.
Запуск: python manage.py test shop
"""
import json
from decimal import Decimal
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse

from .models import Category, Product, Cart, CartItem, Order, OrderItem


@override_settings(ALLOWED_HOSTS=['*'])
class ProductModelTest(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name='Тест', slug='test')
        self.product = Product.objects.create(
            name='Тестовый товар',
            sku='TST-001',
            price=Decimal('990000'),
            category=self.cat,
            is_active=True,
            in_stock=True,
        )

    def test_product_str(self):
        self.assertEqual(str(self.product), 'Тестовый товар')

    def test_product_display_price(self):
        self.assertIn('сум', self.product.display_price)

    def test_product_is_active(self):
        self.assertTrue(self.product.is_active)


@override_settings(ALLOWED_HOSTS=['*'])
class CartModelTest(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='Товар', sku='P-001', price=Decimal('100000'),
            is_active=True, in_stock=True,
        )
        self.cart = Cart.objects.create(telegram_user_id=12345)

    def test_cart_empty(self):
        self.assertEqual(self.cart.total, 0)
        self.assertEqual(self.cart.item_count, 0)

    def test_cart_add_item(self):
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=2)
        self.assertEqual(self.cart.item_count, 2)
        self.assertEqual(self.cart.total, Decimal('200000'))

    def test_cart_item_subtotal(self):
        item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=3)
        self.assertEqual(item.subtotal, Decimal('300000'))


@override_settings(ALLOWED_HOSTS=['*'])
class OrderModelTest(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='Товар', sku='P-001', price=Decimal('500000'),
            is_active=True, in_stock=True,
        )

    def test_order_creation(self):
        order = Order.objects.create(
            telegram_user_id=99999,
            total_price=Decimal('1000000'),
            status='new',
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            product_sku=self.product.sku,
            price=self.product.price,
            quantity=2,
        )
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.status_display, 'Новый')

    def test_order_item_subtotal(self):
        order = Order.objects.create(
            telegram_user_id=99999, total_price=Decimal('0')
        )
        item = OrderItem.objects.create(
            order=order, product=self.product,
            product_name='Товар', product_sku='P-001',
            price=Decimal('500000'), quantity=3,
        )
        self.assertEqual(item.subtotal, Decimal('1500000'))


@override_settings(ALLOWED_HOSTS=['*'])
class DashboardViewTest(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.admin = User.objects.create_superuser(
            username='testadmin', password='testpass123', email='a@b.com'
        )

    def test_login_page(self):
        r = self.client.get('/dashboard/login/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Megamix')

    def test_login_redirect(self):
        r = self.client.post('/dashboard/login/', {
            'username': 'testadmin', 'password': 'testpass123'
        })
        self.assertEqual(r.status_code, 302)

    def test_dashboard_requires_login(self):
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 302)

    def test_dashboard_index(self):
        self.client.login(username='testadmin', password='testpass123')
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Обзор')

    def test_dashboard_products(self):
        self.client.login(username='testadmin', password='testpass123')
        r = self.client.get('/dashboard/products/')
        self.assertEqual(r.status_code, 200)

    def test_dashboard_orders(self):
        self.client.login(username='testadmin', password='testpass123')
        r = self.client.get('/dashboard/orders/')
        self.assertEqual(r.status_code, 200)

    def test_dashboard_analytics(self):
        self.client.login(username='testadmin', password='testpass123')
        r = self.client.get('/dashboard/analytics/')
        self.assertEqual(r.status_code, 200)


@override_settings(ALLOWED_HOSTS=['*'])
class APITest(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.product = Product.objects.create(
            name='API Товар', sku='API-001', price=Decimal('250000'),
            is_active=True, in_stock=True,
        )

    def test_products_api(self):
        r = self.client.get('/api/products/')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertIn('products', data)
        self.assertEqual(len(data['products']), 1)

    def test_cart_api_get(self):
        r = self.client.get('/api/cart/111111/')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertEqual(data['items'], [])

    def test_cart_add_product(self):
        r = self.client.post(
            '/api/cart/111111/add/',
            data=json.dumps({'product_id': self.product.id, 'quantity': 2}),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['item_count'], 2)

    def test_cart_add_invalid_json(self):
        r = self.client.post(
            '/api/cart/111111/add/',
            data='not json',
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

    def test_cart_add_missing_product(self):
        r = self.client.post(
            '/api/cart/111111/add/',
            data=json.dumps({'quantity': 1}),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

    def test_cart_update(self):
        # First add item
        self.client.post(
            '/api/cart/222222/add/',
            data=json.dumps({'product_id': self.product.id, 'quantity': 1}),
            content_type='application/json'
        )
        cart = Cart.objects.get(telegram_user_id=222222)
        item = cart.items.first()
        # Update quantity
        r = self.client.post(
            '/api/cart/222222/update/',
            data=json.dumps({'item_id': item.id, 'quantity': 3}),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

    def test_cart_remove_item(self):
        self.client.post(
            '/api/cart/333333/add/',
            data=json.dumps({'product_id': self.product.id, 'quantity': 1}),
            content_type='application/json'
        )
        cart = Cart.objects.get(telegram_user_id=333333)
        item = cart.items.first()
        r = self.client.delete(f'/api/cart/333333/remove/{item.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(cart.items.count(), 0)

    def test_create_order(self):
        # Add item to cart first
        self.client.post(
            '/api/cart/444444/add/',
            data=json.dumps({'product_id': self.product.id, 'quantity': 1}),
            content_type='application/json'
        )
        r = self.client.post(
            '/api/order/444444/create/',
            data=json.dumps({
                'username': 'testuser',
                'full_name': 'Тест Тестов',
                'phone': '+998901234567',
                'address': 'г. Ташкент',
            }),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertTrue(data['success'])
        order = Order.objects.get(id=data['order_id'])
        self.assertEqual(order.telegram_user_id, 444444)
        self.assertEqual(order.items.count(), 1)

    def test_webapp_index(self):
        r = self.client.get('/webapp/')
        self.assertEqual(r.status_code, 200)

    def test_webapp_cart(self):
        r = self.client.get('/webapp/cart/')
        self.assertEqual(r.status_code, 200)
