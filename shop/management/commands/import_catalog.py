"""
Django management command to import the product catalog from PDF.
Usage: python manage.py import_catalog [pdf_path_or_url]
"""
import sys
from pathlib import Path
from django.core.management.base import BaseCommand

# Reuse the standalone import script logic
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))


class Command(BaseCommand):
    help = 'Импортировать товары из PDF каталога Megamix'

    def add_arguments(self, parser):
        parser.add_argument(
            'source',
            nargs='?',
            default='https://megamix.uz/upload/files/catalog.pdf',
            help='Путь к PDF-файлу или URL (по умолчанию: официальный каталог megamix.uz)'
        )
        parser.add_argument(
            '--no-update',
            action='store_true',
            help='Не обновлять существующие товары, только добавлять новые'
        )

    def handle(self, *args, **options):
        import import_catalog as ic

        source = options['source']
        update_existing = not options['no_update']

        self.stdout.write(f"Источник: {source}")
        tmp_file = None

        try:
            import requests
            from pathlib import Path as P

            if source.startswith('http://') or source.startswith('https://'):
                tmp_file = ic.download_pdf(source)
                pdf_path = tmp_file
            else:
                pdf_path = source

            if not P(pdf_path).exists():
                self.stderr.write(self.style.ERROR(f"Файл не найден: {pdf_path}"))
                return

            self.stdout.write("Парсинг PDF...")
            products = ic.extract_products_from_pdf(pdf_path)

            if not products:
                self.stdout.write(self.style.WARNING("Товары не найдены в PDF."))
                return

            products = ic.deduplicate(products)
            self.stdout.write(f"Найдено уникальных товаров: {len(products)}")

            self.stdout.write("Импорт в базу данных...")
            stats = ic.import_products(products, update_existing=update_existing)

            self.stdout.write(self.style.SUCCESS(
                f"\n✅ Импорт завершён:\n"
                f"   Создано:   {stats['created']}\n"
                f"   Обновлено: {stats['updated']}\n"
                f"   Пропущено: {stats['skipped']}"
            ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Ошибка: {e}"))
        finally:
            if tmp_file:
                from pathlib import Path as P
                if P(tmp_file).exists():
                    P(tmp_file).unlink()
