import json
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
import logging

from .models import Product, Category, Cart, CartItem, Order, OrderItem
from .telegram_auth import get_user_id_from_request

logger = logging.getLogger(__name__)


# ─── Helpers ────────────────────────────────────────────────────────────────

def is_admin(user):
    return user.is_staff or user.is_superuser


def _json_error(msg, status=400):
    return JsonResponse({'success': False, 'error': msg}, status=status)


def _parse_json_body(request):
    """Safely parse request body as JSON."""
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, 'Неверный формат JSON'


# ─── Telegram Mini WebApp ────────────────────────────────────────────────────

@xframe_options_exempt
def webapp_index(request):
    """Main page of the Telegram mini web app — product catalogue."""
    categories = Category.objects.prefetch_related('products').all()
    products = Product.objects.filter(is_active=True).select_related('category')
    category_id = request.GET.get('category')
    search = request.GET.get('q', '')
    if category_id:
        products = products.filter(category_id=category_id)
    if search:
        products = products.filter(
            Q(name__icontains=search) | Q(sku__icontains=search)
        )
    return render(request, 'webapp/index.html', {
        'products': products,
        'categories': categories,
        'selected_category': category_id,
        'search': search,
    })


@xframe_options_exempt
def webapp_cart(request):
    """Cart page of the Telegram mini web app."""
    return render(request, 'webapp/cart.html')


# ─── Cart API (for WebApp & Bot) ─────────────────────────────────────────────

@csrf_exempt
@xframe_options_exempt
@require_http_methods(['GET'])
def api_cart_get(request, user_id):
    verified_id = get_user_id_from_request(request, user_id)
    if verified_id is None:
        return _json_error('Unauthorized', status=403)

    cart, _ = Cart.objects.get_or_create(telegram_user_id=verified_id)
    items = []
    for item in cart.items.select_related('product'):
        items.append({
            'id': item.id,
            'product_id': item.product.id,
            'name': item.product.name,
            'sku': item.product.sku,
            'price': str(item.product.price),
            'quantity': item.quantity,
            'subtotal': str(item.subtotal),
            'photo_url': item.product.photo_url,
        })
    return JsonResponse({
        'items': items,
        'total': str(cart.total),
        'item_count': cart.item_count,
    })


@csrf_exempt
@xframe_options_exempt
@require_http_methods(['POST'])
def api_cart_add(request, user_id):
    verified_id = get_user_id_from_request(request, user_id)
    if verified_id is None:
        return _json_error('Unauthorized', status=403)

    data, err = _parse_json_body(request)
    if data is None:
        return _json_error(f'Invalid JSON: {err}')

    product_id = data.get('product_id')
    if not product_id:
        return _json_error('product_id is required')

    try:
        product_id = int(product_id)
        quantity = max(1, int(data.get('quantity', 1)))
    except (TypeError, ValueError):
        return _json_error('Invalid product_id or quantity')

    product = get_object_or_404(Product, id=product_id, is_active=True)
    cart, _ = Cart.objects.get_or_create(telegram_user_id=verified_id)
    item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    if not created:
        item.quantity += quantity
    else:
        item.quantity = quantity
    item.save()
    return JsonResponse({'success': True, 'item_count': cart.item_count})


@csrf_exempt
@xframe_options_exempt
@require_http_methods(['POST'])
def api_cart_update(request, user_id):
    verified_id = get_user_id_from_request(request, user_id)
    if verified_id is None:
        return _json_error('Unauthorized', status=403)

    data, err = _parse_json_body(request)
    if data is None:
        return _json_error(f'Invalid JSON: {err}')

    item_id = data.get('item_id')
    if not item_id:
        return _json_error('item_id is required')

    try:
        item_id = int(item_id)
        quantity = int(data.get('quantity', 1))
    except (TypeError, ValueError):
        return _json_error('Invalid item_id or quantity')

    cart = get_object_or_404(Cart, telegram_user_id=verified_id)
    item = get_object_or_404(CartItem, id=item_id, cart=cart)
    if quantity <= 0:
        item.delete()
    else:
        item.quantity = quantity
        item.save()
    return JsonResponse({'success': True, 'total': str(cart.total)})


@csrf_exempt
@xframe_options_exempt
@require_http_methods(['DELETE'])
def api_cart_remove(request, user_id, item_id):
    verified_id = get_user_id_from_request(request, user_id)
    if verified_id is None:
        return _json_error('Unauthorized', status=403)

    cart = get_object_or_404(Cart, telegram_user_id=verified_id)
    CartItem.objects.filter(id=item_id, cart=cart).delete()
    return JsonResponse({'success': True, 'total': str(cart.total)})


@csrf_exempt
@xframe_options_exempt
@require_http_methods(['POST'])
def api_cart_clear(request, user_id):
    verified_id = get_user_id_from_request(request, user_id)
    if verified_id is None:
        return _json_error('Unauthorized', status=403)

    cart = get_object_or_404(Cart, telegram_user_id=verified_id)
    cart.items.all().delete()
    return JsonResponse({'success': True})


# ─── Order API ───────────────────────────────────────────────────────────────

@csrf_exempt
@xframe_options_exempt
@require_http_methods(['POST'])
def api_order_create(request, user_id):
    verified_id = get_user_id_from_request(request, user_id)
    if verified_id is None:
        return _json_error('Unauthorized', status=403)

    data, err = _parse_json_body(request)
    if data is None:
        return _json_error(f'Invalid JSON: {err}')

    cart = get_object_or_404(Cart, telegram_user_id=verified_id)
    items = list(cart.items.select_related('product'))
    if not items:
        return _json_error('Корзина пуста', status=400)

    total = cart.total
    order = Order.objects.create(
        telegram_user_id=verified_id,
        telegram_username=str(data.get('username', ''))[:200],
        full_name=str(data.get('full_name', ''))[:300],
        phone=str(data.get('phone', ''))[:50],
        address=str(data.get('address', '')),
        comment=str(data.get('comment', '')),
        total_price=total,
    )
    for item in items:
        OrderItem.objects.create(
            order=order,
            product=item.product,
            product_name=item.product.name,
            product_sku=item.product.sku,
            price=item.product.price,
            quantity=item.quantity,
        )
    cart.items.all().delete()
    return JsonResponse({'success': True, 'order_id': order.id})


@require_http_methods(['GET'])
def api_products(request):
    """Public API: product list with optional category filter."""
    products = Product.objects.filter(is_active=True).select_related('category')
    category_id = request.GET.get('category')
    search = request.GET.get('q', '')
    if category_id:
        products = products.filter(category_id=category_id)
    if search:
        products = products.filter(
            Q(name__icontains=search) | Q(sku__icontains=search)
        )
    data = []
    for p in products:
        data.append({
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'price': str(p.price),
            'description': p.description,
            'photo_url': p.photo_url,
            'in_stock': p.in_stock,
            'category': p.category.name if p.category else '',
        })
    categories = [{'id': c.id, 'name': c.name} for c in Category.objects.all()]
    return JsonResponse({'products': data, 'categories': categories})


# ─── Admin Dashboard ─────────────────────────────────────────────────────────

def dashboard_login(request):
    if request.user.is_authenticated and is_admin(request.user):
        return redirect('dashboard_index')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user and is_admin(user):
            login(request, user)
            return redirect('dashboard_index')
        error = 'Неверный логин или пароль, либо нет прав доступа.'
    return render(request, 'dashboard/login.html', {'error': error})


def dashboard_logout(request):
    logout(request)
    return redirect('dashboard_login')


@login_required
@user_passes_test(is_admin)
def dashboard_index(request):
    now = timezone.now()
    last_30 = now - timedelta(days=30)

    total_orders = Order.objects.count()
    new_orders = Order.objects.filter(status='new').count()
    orders_30d = Order.objects.filter(created_at__gte=last_30).count()
    revenue_30d = Order.objects.filter(
        created_at__gte=last_30
    ).aggregate(total=Sum('total_price'))['total'] or 0

    total_products = Product.objects.filter(is_active=True).count()
    recent_orders = Order.objects.order_by('-created_at')[:10]

    daily_data = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        count = Order.objects.filter(created_at__gte=start, created_at__lt=end).count()
        daily_data.append({'day': start.strftime('%d.%m'), 'count': count})

    return render(request, 'dashboard/index.html', {
        'total_orders': total_orders,
        'new_orders': new_orders,
        'orders_30d': orders_30d,
        'revenue_30d': revenue_30d,
        'total_products': total_products,
        'recent_orders': recent_orders,
        'daily_data': json.dumps(daily_data),
        'active_page': 'index',
    })


@login_required
@user_passes_test(is_admin)
def dashboard_products(request):
    query = request.GET.get('q', '')
    category_id = request.GET.get('category', '')
    products = Product.objects.select_related('category').order_by('name')
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query))
    if category_id:
        products = products.filter(category_id=category_id)
    categories = Category.objects.all()
    return render(request, 'dashboard/products.html', {
        'products': products,
        'categories': categories,
        'query': query,
        'selected_category': category_id,
        'active_page': 'products',
    })


@login_required
@user_passes_test(is_admin)
def dashboard_product_edit(request, pk=None):
    if pk:
        product = get_object_or_404(Product, pk=pk)
    else:
        product = None

    categories = Category.objects.all()

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        sku = request.POST.get('sku', '').strip()
        description = request.POST.get('description', '').strip()
        price_raw = request.POST.get('price', '0').replace(',', '.').strip()
        old_price_raw = request.POST.get('old_price', '').replace(',', '.').strip()
        image_url = request.POST.get('image_url', '').strip()
        category_id = request.POST.get('category', '')
        in_stock = request.POST.get('in_stock') == 'on'
        is_active = request.POST.get('is_active') == 'on'

        if product is None:
            product = Product()

        product.name = name
        product.sku = sku
        product.description = description
        try:
            product.price = Decimal(price_raw)
        except (InvalidOperation, ValueError):
            product.price = Decimal('0')
        try:
            product.old_price = Decimal(old_price_raw) if old_price_raw else None
        except (InvalidOperation, ValueError):
            product.old_price = None
        product.image_url = image_url
        product.in_stock = in_stock
        product.is_active = is_active
        if category_id:
            try:
                product.category_id = int(category_id)
            except ValueError:
                product.category = None
        else:
            product.category = None

        if 'image' in request.FILES:
            product.image = request.FILES['image']

        product.save()
        return redirect('dashboard_products')

    return render(request, 'dashboard/product_edit.html', {
        'product': product,
        'categories': categories,
        'active_page': 'products',
    })


@login_required
@user_passes_test(is_admin)
def dashboard_product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.delete()
    return redirect('dashboard_products')


@login_required
@user_passes_test(is_admin)
def dashboard_orders(request):
    status_filter = request.GET.get('status', '')
    orders = Order.objects.prefetch_related('items').order_by('-created_at')
    if status_filter:
        orders = orders.filter(status=status_filter)
    return render(request, 'dashboard/orders.html', {
        'orders': orders,
        'status_filter': status_filter,
        'status_choices': Order.STATUS_CHOICES,
        'active_page': 'orders',
    })


@login_required
@user_passes_test(is_admin)
def dashboard_order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(Order.STATUS_CHOICES):
            order.status = new_status
            order.save()
        return redirect('dashboard_order_detail', pk=pk)
    return render(request, 'dashboard/order_detail.html', {
        'order': order,
        'status_choices': Order.STATUS_CHOICES,
        'active_page': 'orders',
    })


@login_required
@user_passes_test(is_admin)
def dashboard_analytics(request):
    now = timezone.now()
    periods = {
        '7d': now - timedelta(days=7),
        '30d': now - timedelta(days=30),
        '90d': now - timedelta(days=90),
    }
    period = request.GET.get('period', '30d')
    since = periods.get(period, periods['30d'])

    orders = Order.objects.filter(created_at__gte=since)
    total_orders = orders.count()
    total_revenue = orders.aggregate(total=Sum('total_price'))['total'] or 0
    avg_order = (total_revenue / total_orders) if total_orders else 0

    status_stats = {}
    for s, label in Order.STATUS_CHOICES:
        status_stats[label] = orders.filter(status=s).count()

    top_products = (
        OrderItem.objects.filter(order__created_at__gte=since)
        .values('product_name')
        .annotate(total_qty=Sum('quantity'), total_rev=Sum('price'))
        .order_by('-total_qty')[:10]
    )

    daily_revenue = []
    for i in range(29, -1, -1):
        day = now - timedelta(days=i)
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        rev = orders.filter(created_at__gte=start, created_at__lt=end).aggregate(
            total=Sum('total_price')
        )['total'] or 0
        daily_revenue.append({'day': start.strftime('%d.%m'), 'revenue': float(rev)})

    return render(request, 'dashboard/analytics.html', {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'avg_order': avg_order,
        'status_stats': status_stats,
        'top_products': top_products,
        'daily_revenue': json.dumps(daily_revenue),
        'period': period,
        'active_page': 'analytics',
    })
