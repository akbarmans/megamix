# 🎵 Megamix — Интернет-магазин на Railway

Полноценная система электронной коммерции с Telegram-ботом, веб-приложением и панелью администратора.

## 🚀 Быстрый старт на Railway

### 1. Подключите репозиторий к Railway

1. Войдите на [railway.app](https://railway.app)
2. Нажмите **New Project → Deploy from GitHub repo**
3. Выберите этот репозиторий

### 2. Добавьте PostgreSQL

1. В проекте нажмите **+ New → Database → PostgreSQL**
2. Railway автоматически установит `DATABASE_URL`

### 3. Настройте переменные окружения

В разделе **Variables** вашего сервиса добавьте:

| Переменная | Описание | Пример |
|---|---|---|
| `SECRET_KEY` | Секретный ключ Django | `your-very-secret-key-here` |
| `DEBUG` | Режим отладки | `False` |
| `ALLOWED_HOSTS` | Разрешённые хосты | `*.railway.app,localhost` |
| `TELEGRAM_TOKEN` | Токен Telegram-бота (от @BotFather) | `1234567890:ABC...` |
| `TELEGRAM_ADMIN_IDS` | Telegram ID администраторов | `123456789,987654321` |
| `WEBAPP_URL` | URL вашего приложения на Railway | `https://your-app.up.railway.app` |
| `DATABASE_URL` | Автоматически от Railway | — |

### 4. Запуск

Railway автоматически выполнит миграции и запустит сервер. Для запуска бота:

```bash
# Локально (разработка)
python manage.py migrate
python manage.py runserver &
python bot.py

# Создать суперпользователя для панели администратора
python manage.py createsuperuser

# Импорт каталога товаров из PDF
python import_catalog.py
# или через Django:
python manage.py import_catalog
```

---

## 📁 Структура проекта

```
megamix/
├── config/              # Настройки Django
│   ├── settings.py
│   └── urls.py
├── shop/                # Основное приложение
│   ├── models.py        # Модели: Product, Cart, Order, ...
│   ├── views.py         # Представления (API + dashboard)
│   ├── urls.py          # URL-маршруты
│   └── templates/
│       ├── dashboard/   # Панель администратора (русский интерфейс)
│       └── webapp/      # Telegram Mini Web App
├── static/css/          # Стили
├── bot.py               # Telegram-бот
├── import_catalog.py    # Скрипт импорта каталога из PDF
├── requirements.txt
├── Procfile             # Railway / Heroku
└── railway.json         # Конфигурация Railway
```

---

## 🤖 Telegram-бот

### Возможности:
- 📦 **Каталог** — просмотр всех товаров с пагинацией
- 🛒 **Корзина** — добавление/удаление/изменение количества
- ✅ **Оформление заказа** — ввод ФИО, телефона, адреса прямо в боте
- 🛍 **Мини веб-приложение** — полноценный магазин прямо в Telegram
- 📋 **Мои заказы** — история заказов пользователя
- 🔔 **Уведомления** — администраторы получают уведомление о каждом заказе

### Команды:
```
/start    — начало работы
/catalog  — каталог товаров
/cart     — корзина
/orders   — мои заказы
/clear    — очистить корзину
/help     — помощь
```

---

## 🌐 Telegram Mini Web App

Интегрированное веб-приложение, доступное прямо в Telegram:
- Каталог товаров с поиском и фильтром по категориям
- Добавление/изменение количества прямо из каталога
- Синхронизация корзины с ботом (единая база данных)
- Оформление заказа с контактными данными

URL: `https://your-app.up.railway.app/webapp/`

---

## 📊 Панель администратора

Веб-интерфейс для управления магазином:

| URL | Описание |
|---|---|
| `/dashboard/` | Обзор: статистика, последние заказы |
| `/dashboard/products/` | Список товаров, редактирование цен |
| `/dashboard/orders/` | Все заказы с фильтром по статусу |
| `/dashboard/analytics/` | Аналитика: выручка, топ товаров |

**Вход:** создайте суперпользователя командой `python manage.py createsuperuser`

---

## 📦 Импорт каталога

Скрипт автоматически парсит PDF-каталог и импортирует товары:

```bash
# Загрузить с официального сайта
python import_catalog.py

# Из локального файла
python import_catalog.py catalog.pdf

# Из произвольного URL
python import_catalog.py https://example.com/catalog.pdf

# Через Django команду (только добавить новые, не обновлять)
python manage.py import_catalog --no-update
```

---

## 🔧 Локальная разработка

```bash
# 1. Клонировать репозиторий
git clone https://github.com/akbarmans/megamix.git
cd megamix

# 2. Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или: venv\Scripts\activate  # Windows

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Создать .env файл
cp .env.example .env
# Заполните .env своими данными

# 5. Применить миграции
python manage.py migrate

# 6. Создать администратора
python manage.py createsuperuser

# 7. (Опционально) Импортировать каталог
python import_catalog.py

# 8. Запустить сервер и бот
python manage.py runserver &
python bot.py
```

---

## 🗄️ Модели данных

| Модель | Описание |
|---|---|
| `Category` | Категории товаров |
| `Product` | Товары (название, SKU, цена, фото) |
| `Cart` | Корзина пользователя (по Telegram ID) |
| `CartItem` | Позиция в корзине |
| `Order` | Заказ |
| `OrderItem` | Позиция в заказе |

---

## 🔐 Безопасность

- Никогда не публикуйте `.env` файл с реальными данными
- Используйте сложный `SECRET_KEY` в продакшене
- Установите `DEBUG=False` на продакшене
- Регулярно обновляйте зависимости

---

## 📄 Лицензия

MIT License — используйте свободно.
