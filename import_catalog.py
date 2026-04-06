#!/usr/bin/env python
"""
Скрипт импорта каталога товаров из PDF-файла.
Использование:
    python import_catalog.py [path_to_pdf_or_url]

По умолчанию загружает: https://megamix.uz/upload/files/catalog.pdf

Пример:
    python import_catalog.py
    python import_catalog.py catalog.pdf
    python import_catalog.py https://megamix.uz/upload/files/catalog.pdf
"""
import os
import sys
import re
import django
import logging
import requests
import tempfile
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from shop.models import Product, Category

try:
    import pdfplumber
except ImportError:
    print("Установите pdfplumber: pip install pdfplumber")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_PDF_URL = "https://megamix.uz/upload/files/catalog.pdf"


def download_pdf(url: str) -> str:
    """Download PDF to a temp file and return its path."""
    logger.info(f"Загрузка PDF: {url}")
    r = requests.get(url, timeout=60, stream=True)
    r.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    for chunk in r.iter_content(chunk_size=8192):
        tmp.write(chunk)
    tmp.close()
    logger.info(f"PDF сохранён: {tmp.name}")
    return tmp.name


def extract_products_from_pdf(pdf_path: str) -> list:
    """
    Parse product entries from the PDF.
    Tries multiple heuristics to detect product rows.
    Returns list of dicts: {name, sku, price, description, category}.
    """
    products = []
    current_category = "Общее"

    # Price pattern: number with possible spaces/commas, ending in сум/som/UZS or standalone
    price_re = re.compile(
        r'(\d[\d\s,\.]*\d)\s*(?:сум|som|uzs|руб\.?|₽|usd|\$|€)?',
        re.IGNORECASE
    )
    # SKU patterns
    sku_re = re.compile(r'\b([A-Z]{1,5}[-_]?\d{3,}(?:[-_][A-Z0-9]+)?)\b')

    with pdfplumber.open(pdf_path) as pdf:
        logger.info(f"Страниц в PDF: {len(pdf.pages)}")

        for page_num, page in enumerate(pdf.pages, 1):
            # Try to extract table data first
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        row = [cell or '' for cell in row]
                        row_text = ' | '.join(str(c).strip() for c in row if str(c).strip())

                        if not row_text or len(row_text) < 3:
                            continue

                        name = ''
                        sku = ''
                        price = None
                        description = ''

                        # Attempt to detect columns
                        if len(row) >= 3:
                            # Assume: name | sku/description | price or name | price
                            name = str(row[0]).strip()
                            last_col = str(row[-1]).strip()
                            m = price_re.search(last_col)
                            if m:
                                price_str = re.sub(r'[\s,]', '', m.group(1))
                                try:
                                    price = float(price_str)
                                except ValueError:
                                    price = None
                            if len(row) >= 3:
                                middle = str(row[1]).strip()
                                sku_m = sku_re.search(middle)
                                if sku_m:
                                    sku = sku_m.group(1)
                                    description = middle
                                else:
                                    description = middle
                        elif len(row) == 2:
                            name = str(row[0]).strip()
                            m = price_re.search(str(row[1]))
                            if m:
                                price_str = re.sub(r'[\s,]', '', m.group(1))
                                try:
                                    price = float(price_str)
                                except ValueError:
                                    price = None

                        if name and price is not None and price > 0:
                            sku_m2 = sku_re.search(name)
                            if sku_m2 and not sku:
                                sku = sku_m2.group(1)
                            products.append({
                                'name': name,
                                'sku': sku,
                                'price': price,
                                'description': description,
                                'category': current_category,
                            })
            else:
                # Fallback: parse raw text
                text = page.extract_text() or ''
                lines = [l.strip() for l in text.splitlines() if l.strip()]

                for line in lines:
                    # Detect category headers (short, all caps, no price)
                    if len(line) < 60 and line.isupper() and not price_re.search(line):
                        current_category = line.title()
                        continue

                    m = price_re.search(line)
                    if m:
                        price_str = re.sub(r'[\s,]', '', m.group(1))
                        try:
                            price = float(price_str)
                        except ValueError:
                            continue
                        if price <= 0:
                            continue

                        name = line[:m.start()].strip().rstrip('.-–—')
                        if len(name) < 3:
                            continue

                        sku = ''
                        sku_m = sku_re.search(name)
                        if sku_m:
                            sku = sku_m.group(1)

                        products.append({
                            'name': name,
                            'sku': sku,
                            'price': price,
                            'description': '',
                            'category': current_category,
                        })

    logger.info(f"Найдено товаров в PDF: {len(products)}")
    return products


def deduplicate(products: list) -> list:
    seen = set()
    result = []
    for p in products:
        key = (p['name'].lower(), str(p['price']))
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def import_products(products: list, update_existing: bool = True) -> dict:
    """Import products into the database."""
    created_count = 0
    updated_count = 0
    skipped_count = 0
    category_cache = {}

    for item in products:
        cat_name = item.get('category', 'Общее') or 'Общее'
        if cat_name not in category_cache:
            cat, _ = Category.objects.get_or_create(
                name=cat_name,
                defaults={'slug': re.sub(r'[^\w]', '-', cat_name.lower())[:200]}
            )
            category_cache[cat_name] = cat
        category = category_cache[cat_name]

        name = item['name']
        sku = item.get('sku', '')
        price = item['price']

        if not name or price <= 0:
            skipped_count += 1
            continue

        # Find existing product
        existing = None
        if sku:
            existing = Product.objects.filter(sku=sku).first()
        if not existing:
            existing = Product.objects.filter(name__iexact=name).first()

        if existing:
            if update_existing:
                existing.price = price
                existing.category = category
                if item.get('description'):
                    existing.description = item['description']
                if sku and not existing.sku:
                    existing.sku = sku
                existing.save()
                updated_count += 1
            else:
                skipped_count += 1
        else:
            Product.objects.create(
                name=name,
                sku=sku,
                price=price,
                description=item.get('description', ''),
                category=category,
                in_stock=True,
                is_active=True,
            )
            created_count += 1

    return {
        'created': created_count,
        'updated': updated_count,
        'skipped': skipped_count,
    }


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF_URL
    tmp_file = None

    try:
        if source.startswith('http://') or source.startswith('https://'):
            tmp_file = download_pdf(source)
            pdf_path = tmp_file
        else:
            pdf_path = source

        if not Path(pdf_path).exists():
            logger.error(f"Файл не найден: {pdf_path}")
            sys.exit(1)

        logger.info("Парсинг PDF...")
        products = extract_products_from_pdf(pdf_path)

        if not products:
            logger.warning(
                "Товары не найдены в PDF. "
                "Возможно, PDF имеет нестандартный формат. "
                "Проверьте структуру файла вручную."
            )
            sys.exit(0)

        products = deduplicate(products)
        logger.info(f"Уникальных товаров: {len(products)}")

        logger.info("Импорт в базу данных...")
        stats = import_products(products)

        logger.info(
            f"✅ Импорт завершён:\n"
            f"   Создано:  {stats['created']}\n"
            f"   Обновлено: {stats['updated']}\n"
            f"   Пропущено: {stats['skipped']}"
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка загрузки PDF: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Ошибка при импорте: {e}")
        sys.exit(1)
    finally:
        if tmp_file and Path(tmp_file).exists():
            Path(tmp_file).unlink()


if __name__ == '__main__':
    main()
