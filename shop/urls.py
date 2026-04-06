from django.urls import path
from . import views

urlpatterns = [
    # Telegram Mini WebApp
    path('webapp/', views.webapp_index, name='webapp_index'),
    path('webapp/cart/', views.webapp_cart, name='webapp_cart'),

    # Cart API
    path('api/cart/<int:user_id>/', views.api_cart_get, name='api_cart_get'),
    path('api/cart/<int:user_id>/add/', views.api_cart_add, name='api_cart_add'),
    path('api/cart/<int:user_id>/update/', views.api_cart_update, name='api_cart_update'),
    path('api/cart/<int:user_id>/remove/<int:item_id>/', views.api_cart_remove, name='api_cart_remove'),
    path('api/cart/<int:user_id>/clear/', views.api_cart_clear, name='api_cart_clear'),

    # Order API
    path('api/order/<int:user_id>/create/', views.api_order_create, name='api_order_create'),

    # Products API
    path('api/products/', views.api_products, name='api_products'),

    # Dashboard
    path('dashboard/login/', views.dashboard_login, name='dashboard_login'),
    path('dashboard/logout/', views.dashboard_logout, name='dashboard_logout'),
    path('dashboard/', views.dashboard_index, name='dashboard_index'),
    path('dashboard/products/', views.dashboard_products, name='dashboard_products'),
    path('dashboard/products/add/', views.dashboard_product_edit, name='dashboard_product_add'),
    path('dashboard/products/<int:pk>/edit/', views.dashboard_product_edit, name='dashboard_product_edit'),
    path('dashboard/products/<int:pk>/delete/', views.dashboard_product_delete, name='dashboard_product_delete'),
    path('dashboard/orders/', views.dashboard_orders, name='dashboard_orders'),
    path('dashboard/orders/<int:pk>/', views.dashboard_order_detail, name='dashboard_order_detail'),
    path('dashboard/analytics/', views.dashboard_analytics, name='dashboard_analytics'),
]
