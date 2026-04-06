from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=200, verbose_name='Название')
    slug = models.SlugField(max_length=200, unique=True, blank=True)

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='products', verbose_name='Категория'
    )
    name = models.CharField(max_length=500, verbose_name='Название')
    sku = models.CharField(max_length=100, blank=True, verbose_name='Артикул')
    description = models.TextField(blank=True, verbose_name='Описание')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Цена')
    old_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Старая цена'
    )
    image_url = models.URLField(max_length=1000, blank=True, verbose_name='Ссылка на фото')
    image = models.ImageField(upload_to='products/', null=True, blank=True, verbose_name='Фото')
    in_stock = models.BooleanField(default=True, verbose_name='В наличии')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def display_price(self):
        return f"{self.price:,.0f} сум"

    @property
    def photo_url(self):
        if self.image:
            return self.image.url
        return self.image_url or ''


class Cart(models.Model):
    telegram_user_id = models.BigIntegerField(verbose_name='Telegram ID')
    telegram_username = models.CharField(max_length=200, blank=True, verbose_name='Username')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Корзина'
        verbose_name_plural = 'Корзины'

    def __str__(self):
        return f"Корзина пользователя {self.telegram_user_id}"

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Товар')
    quantity = models.PositiveIntegerField(default=1, verbose_name='Количество')

    class Meta:
        verbose_name = 'Элемент корзины'
        verbose_name_plural = 'Элементы корзины'
        unique_together = ('cart', 'product')

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    @property
    def subtotal(self):
        return self.product.price * self.quantity


class Order(models.Model):
    STATUS_CHOICES = [
        ('new', 'Новый'),
        ('confirmed', 'Подтверждён'),
        ('processing', 'В обработке'),
        ('shipped', 'Отправлен'),
        ('delivered', 'Доставлен'),
        ('cancelled', 'Отменён'),
    ]

    telegram_user_id = models.BigIntegerField(verbose_name='Telegram ID')
    telegram_username = models.CharField(max_length=200, blank=True, verbose_name='Username')
    full_name = models.CharField(max_length=300, blank=True, verbose_name='ФИО')
    phone = models.CharField(max_length=50, blank=True, verbose_name='Телефон')
    address = models.TextField(blank=True, verbose_name='Адрес')
    comment = models.TextField(blank=True, verbose_name='Комментарий')
    total_price = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Сумма заказа')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='new', verbose_name='Статус'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']

    def __str__(self):
        return f"Заказ #{self.pk} от {self.telegram_user_id}"

    @property
    def status_display(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, verbose_name='Товар'
    )
    product_name = models.CharField(max_length=500, verbose_name='Название товара')
    product_sku = models.CharField(max_length=100, blank=True, verbose_name='Артикул')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Цена')
    quantity = models.PositiveIntegerField(default=1, verbose_name='Количество')

    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказа'

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"

    @property
    def subtotal(self):
        return self.price * self.quantity
