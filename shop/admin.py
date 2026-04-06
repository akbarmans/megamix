from django.contrib import admin
from .models import Category, Product, Cart, CartItem, Order, OrderItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product', 'product_name', 'product_sku', 'price', 'quantity', 'subtotal']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'price', 'category', 'in_stock', 'is_active']
    list_filter = ['category', 'in_stock', 'is_active']
    search_fields = ['name', 'sku']
    list_editable = ['price', 'in_stock', 'is_active']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['pk', 'telegram_user_id', 'full_name', 'phone', 'total_price', 'status', 'created_at']
    list_filter = ['status']
    inlines = [OrderItemInline]
    readonly_fields = ['telegram_user_id', 'telegram_username', 'total_price', 'created_at']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['telegram_user_id', 'telegram_username', 'item_count', 'total', 'updated_at']
