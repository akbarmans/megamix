"""
Утилиты для верификации данных Telegram WebApp.
Документация: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qsl

logger = logging.getLogger(__name__)


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Проверить подлинность initData от Telegram WebApp.
    Возвращает словарь пользователя при успехе, None при ошибке.
    """
    if not init_data or not bot_token:
        return None

    try:
        params = dict(parse_qsl(init_data, strict_parsing=False))
        received_hash = params.pop('hash', None)
        if not received_hash:
            return None

        data_check_string = '\n'.join(
            f'{k}={v}' for k, v in sorted(params.items())
        )
        secret_key = hmac.new(
            b'WebAppData', bot_token.encode('utf-8'), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode('utf-8'), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            logger.warning("Telegram initData validation failed: hash mismatch")
            return None

        user_json = params.get('user', '{}')
        return json.loads(user_json)
    except Exception as e:
        logger.warning(f"Telegram initData validation error: {e}")
        return None


def get_user_id_from_request(request, url_user_id: int) -> int | None:
    """
    Получить и проверить user_id из запроса.
    Если initData присутствует — проверяет подпись и сравнивает ID.
    Если initData нет — просто возвращает user_id из URL (режим разработки).
    """
    from django.conf import settings

    init_data = request.headers.get('X-Telegram-Init-Data', '')
    if not init_data:
        # Fallback: доверяем ID из URL (приемлемо для dev/bot-side вызовов)
        return url_user_id

    user_data = validate_init_data(init_data, settings.TELEGRAM_TOKEN)
    if user_data is None:
        return None  # Неверная подпись

    verified_id = user_data.get('id')
    if verified_id and int(verified_id) != url_user_id:
        logger.warning(
            f"User ID mismatch: URL={url_user_id}, initData={verified_id}"
        )
        return None

    return url_user_id
