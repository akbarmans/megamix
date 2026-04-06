"""
Telegram-бот для магазина Megamix.
Запуск: python bot.py
"""
import os
import sys
import django
import asyncio
import logging
from decimal import Decimal

# ─── Django setup ────────────────────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from shop.models import Product, Category, Cart, CartItem, Order, OrderItem

# ─── Telegram bot imports ────────────────────────────────────────────────────
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── States for ConversationHandler ─────────────────────────────────────────
WAITING_PHONE, WAITING_ADDRESS, WAITING_NAME = range(3)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def fmt_price(v):
    return f"{int(v):,}".replace(',', ' ') + " сум"


def get_or_create_cart(user_id: int, username: str = '') -> Cart:
    cart, _ = Cart.objects.get_or_create(telegram_user_id=user_id)
    if username and not cart.telegram_username:
        cart.telegram_username = username
        cart.save(update_fields=['telegram_username'])
    return cart


def cart_summary_text(cart: Cart) -> str:
    items = list(cart.items.select_related('product'))
    if not items:
        return "🛒 Ваша корзина пуста."
    lines = ["🛒 *Ваша корзина:*\n"]
    for item in items:
        lines.append(
            f"• {item.product.name} × {item.quantity} = {fmt_price(item.subtotal)}"
        )
    lines.append(f"\n💰 *Итого: {fmt_price(cart.total)}*")
    return '\n'.join(lines)


def main_keyboard(webapp_url: str) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton("📦 Каталог"), KeyboardButton("🛒 Корзина")],
        [
            KeyboardButton(
                "🛍 Открыть магазин",
                web_app=WebAppInfo(url=f"{webapp_url}/webapp/")
            )
        ],
        [KeyboardButton("📋 Мои заказы"), KeyboardButton("ℹ️ О нас")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


# ─── Command handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    webapp_url = settings.WEBAPP_URL
    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Добро пожаловать в магазин *Megamix* 🎵\n\n"
        "Используйте меню ниже для навигации:\n"
        "• *📦 Каталог* — просмотреть товары\n"
        "• *🛒 Корзина* — ваша корзина\n"
        "• *🛍 Открыть магазин* — полный интерфейс"
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard(webapp_url)
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ *Помощь*\n\n"
        "📦 *Каталог* — список всех товаров\n"
        "🛒 *Корзина* — управление корзиной\n"
        "🛍 *Открыть магазин* — веб-интерфейс\n"
        "📋 *Мои заказы* — история заказов\n\n"
        "Команды:\n"
        "/start — начало работы\n"
        "/cart — показать корзину\n"
        "/catalog — каталог товаров\n"
        "/orders — мои заказы\n"
        "/clear — очистить корзину"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Show paginated product catalogue."""
    PER_PAGE = 8
    products = list(Product.objects.filter(is_active=True).order_by('name'))
    total = len(products)
    start = page * PER_PAGE
    end = start + PER_PAGE
    current_page_products = products[start:end]

    if not current_page_products:
        msg = "📦 Товары не найдены."
        if update.message:
            await update.message.reply_text(msg)
        else:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg)
        return

    text = f"📦 *Каталог товаров* (страница {page + 1}):\n\n"
    keyboard = []

    for p in current_page_products:
        price_str = fmt_price(p.price)
        sku_str = f" [{p.sku}]" if p.sku else ""
        text += f"• *{p.name}*{sku_str} — {price_str}\n"
        keyboard.append([
            InlineKeyboardButton(
                f"➕ {p.name[:30]}",
                callback_data=f"add:{p.id}"
            )
        ])

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ Назад", callback_data=f"catalog:{page-1}"))
    if end < total:
        nav_row.append(InlineKeyboardButton("Вперёд ▶", callback_data=f"catalog:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("🛒 Перейти в корзину", callback_data="show_cart")])
    markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)


async def show_cart_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show cart with management buttons."""
    user = update.effective_user
    cart = get_or_create_cart(user.id, user.username or '')
    items = list(cart.items.select_related('product'))

    text = cart_summary_text(cart)
    keyboard = []

    for item in items:
        keyboard.append([
            InlineKeyboardButton(f"➖", callback_data=f"dec:{item.id}"),
            InlineKeyboardButton(
                f"{item.product.name[:25]} ×{item.quantity}",
                callback_data="noop"
            ),
            InlineKeyboardButton(f"➕", callback_data=f"inc:{item.id}"),
            InlineKeyboardButton(f"🗑", callback_data=f"del:{item.id}"),
        ])

    if items:
        keyboard.append([
            InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout"),
            InlineKeyboardButton("🗑 Очистить", callback_data="clear_cart"),
        ])

    keyboard.append([
        InlineKeyboardButton("📦 В каталог", callback_data="catalog:0"),
    ])

    markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
    elif update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup
            )
        except Exception:
            pass


# ─── Callback query handlers ──────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    if data == "noop":
        await query.answer()
        return

    cart = get_or_create_cart(user.id, user.username or '')

    if data.startswith("catalog:"):
        page = int(data.split(":")[1])
        await show_catalog(update, context, page)
        return

    if data.startswith("add:"):
        product_id = int(data.split(":")[1])
        try:
            product = Product.objects.get(id=product_id, is_active=True)
            item, created = CartItem.objects.get_or_create(cart=cart, product=product)
            if not created:
                item.quantity += 1
                item.save()
            await query.answer(f"✅ {product.name} добавлен в корзину")
        except Product.DoesNotExist:
            await query.answer("❌ Товар не найден")
        return

    if data.startswith("inc:"):
        item_id = int(data.split(":")[1])
        try:
            item = CartItem.objects.get(id=item_id, cart=cart)
            item.quantity += 1
            item.save()
        except CartItem.DoesNotExist:
            pass
        await show_cart_message(update, context)
        return

    if data.startswith("dec:"):
        item_id = int(data.split(":")[1])
        try:
            item = CartItem.objects.get(id=item_id, cart=cart)
            if item.quantity > 1:
                item.quantity -= 1
                item.save()
            else:
                item.delete()
        except CartItem.DoesNotExist:
            pass
        await show_cart_message(update, context)
        return

    if data.startswith("del:"):
        item_id = int(data.split(":")[1])
        CartItem.objects.filter(id=item_id, cart=cart).delete()
        await show_cart_message(update, context)
        return

    if data == "show_cart":
        await show_cart_message(update, context)
        return

    if data == "clear_cart":
        cart.items.all().delete()
        await query.answer("🗑 Корзина очищена")
        await show_cart_message(update, context)
        return

    if data == "checkout":
        items = list(cart.items.select_related('product'))
        if not items:
            await query.answer("Корзина пуста!")
            return
        await query.answer()
        context.user_data['checkout'] = True
        await query.message.reply_text(
            "📋 *Оформление заказа*\n\nПожалуйста, введите ваше *ФИО*:",
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data['checkout_step'] = 'name'
        return


# ─── Message handler for checkout flow ───────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    webapp_url = settings.WEBAPP_URL

    # Checkout conversation
    step = context.user_data.get('checkout_step')
    if step == 'name':
        context.user_data['order_name'] = text
        context.user_data['checkout_step'] = 'phone'
        await update.message.reply_text(
            "📞 Введите ваш *номер телефона*:",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if step == 'phone':
        context.user_data['order_phone'] = text
        context.user_data['checkout_step'] = 'address'
        await update.message.reply_text(
            "📍 Введите *адрес доставки*:",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if step == 'address':
        context.user_data['order_address'] = text
        context.user_data['checkout_step'] = None
        # Create order
        cart = get_or_create_cart(user.id, user.username or '')
        items = list(cart.items.select_related('product'))
        if not items:
            await update.message.reply_text("❌ Корзина пуста. Добавьте товары.")
            return

        order = Order.objects.create(
            telegram_user_id=user.id,
            telegram_username=user.username or '',
            full_name=context.user_data.get('order_name', ''),
            phone=context.user_data.get('order_phone', ''),
            address=text,
            total_price=cart.total,
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

        # Compose confirmation
        items_text = '\n'.join(
            f"• {oi.product_name} × {oi.quantity} = {fmt_price(oi.subtotal)}"
            for oi in order.items.all()
        )
        confirm_text = (
            f"✅ *Заказ #{order.pk} оформлен!*\n\n"
            f"{items_text}\n\n"
            f"💰 *Итого: {fmt_price(order.total_price)}*\n\n"
            f"👤 ФИО: {order.full_name}\n"
            f"📞 Телефон: {order.phone}\n"
            f"📍 Адрес: {order.address}\n\n"
            "Мы свяжемся с вами в ближайшее время. Спасибо!"
        )
        await update.message.reply_text(
            confirm_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_keyboard(webapp_url)
        )

        # Notify admins
        for admin_id in settings.TELEGRAM_ADMIN_IDS:
            try:
                admin_text = (
                    f"🔔 *Новый заказ #{order.pk}*\n\n"
                    f"{items_text}\n\n"
                    f"💰 *Итого: {fmt_price(order.total_price)}*\n"
                    f"👤 ФИО: {order.full_name}\n"
                    f"📞 Телефон: {order.phone}\n"
                    f"📍 Адрес: {order.address}\n"
                    f"🆔 Telegram: @{user.username or user.id}"
                )
                await context.bot.send_message(
                    admin_id, admin_text, parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.warning(f"Failed to notify admin {admin_id}: {e}")
        return

    # Menu buttons
    if text == "📦 Каталог":
        await show_catalog(update, context, 0)
    elif text == "🛒 Корзина":
        await show_cart_message(update, context)
    elif text == "📋 Мои заказы":
        await show_orders(update, context)
    elif text == "ℹ️ О нас":
        await update.message.reply_text(
            "🎵 *Megamix* — ваш музыкальный магазин!\n\n"
            "Лучшие товары по отличным ценам.\n"
            "Доставка по всему городу.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "Используйте меню для навигации. /help — список команд.",
            reply_markup=main_keyboard(webapp_url)
        )


async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    orders = Order.objects.filter(telegram_user_id=user.id).order_by('-created_at')[:10]
    if not orders:
        await update.message.reply_text("📋 У вас пока нет заказов.")
        return

    lines = ["📋 *Ваши заказы:*\n"]
    for order in orders:
        lines.append(
            f"• Заказ #{order.pk} — {fmt_price(order.total_price)}\n"
            f"  Статус: {order.status_display}\n"
            f"  Дата: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        )
    await update.message.reply_text('\n'.join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_cart_message(update, context)


async def cmd_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_catalog(update, context, 0)


async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_orders(update, context)


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cart = get_or_create_cart(user.id)
    cart.items.all().delete()
    await update.message.reply_text("🗑 Корзина очищена.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    token = settings.TELEGRAM_TOKEN
    if not token:
        logger.error("TELEGRAM_TOKEN не задан в переменных окружения!")
        sys.exit(1)

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cart", cmd_cart))
    app.add_handler(CommandHandler("catalog", cmd_catalog))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
