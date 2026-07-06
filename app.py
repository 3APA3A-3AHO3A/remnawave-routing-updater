import os
import json
import time
import base64
import requests

from config import *
from logger import logger


def get_template():
    try:
        with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Не удалось прочитать шаблон {TEMPLATE_PATH}: {e}")
        return None


def update_routing():
    logger.info("Начинаем процесс обновления роутинга...")

    template = get_template()
    if not template:
        return

    # 1. Обновляем метку времени (LastUpdated)
    template["LastUpdated"] = str(int(time.time()))

    # 2. Сохраняем routing.json (для autorouting INCY)
    try:
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2)
        logger.info(f"Файл {OUTPUT_PATH} успешно сохранен.")
    except Exception as e:
        logger.error(f"Ошибка сохранения файла: {e}")
        return

    # 3. Генерируем Base64
    json_str = json.dumps(template, separators=(',', ':'))
    b64_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

    happ_routing_link = f"happ://routing/onadd/{b64_str}"
    incy_routing_link = f"incy://routing/onadd/{b64_str}"
    incy_autorouting_link = f"incy://autorouting/onadd/{AUTOROUTING_URL}"

    # 4. Обращение к API Remnawave
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        api_url = f"{PANEL_URL}/api/subscription-settings"

        # Шаг А: Получаем текущие настройки целиком
        resp = requests.get(api_url, headers=headers)
        resp.raise_for_status()

        data = resp.json().get("response")
        if not data:
            logger.error("Ошибка API: Не найден объект 'response' в ответе сервера.")
            return

        # Шаг Б: Модифицируем данные
        updated_headers_count = 0

        # Обновляем дефолтное поле Happ (чтобы работало из коробки у всех)
        data["happRouting"] = happ_routing_link

        # Обновляем кастомные хэдеры (если они есть)
        if "responseRules" in data and "rules" in data["responseRules"]:
            for rule in data["responseRules"]["rules"]:
                rule_name = rule.get("name")

                if rule_name in ["Incy", "Happ"]:
                    modifications = rule.setdefault("responseModifications", {})
                    resp_headers = modifications.setdefault("headers", [])

                    if rule_name == "Incy":
                        for h in resp_headers:
                            if h["key"] == "routing":
                                h["value"] = incy_routing_link
                                updated_headers_count += 1
                            elif h["key"] == "autorouting":
                                h["value"] = incy_autorouting_link
                                updated_headers_count += 1

                    if rule_name == "Happ":
                        for h in resp_headers:
                            if h["key"] == "routing":
                                h["value"] = happ_routing_link
                                updated_headers_count += 1

        # Шаг В: Отправляем измененный объект целиком обратно
        patch_resp = requests.patch(api_url, headers=headers, json=data)
        patch_resp.raise_for_status()

        logger.info(f"✅ База Remnawave успешно обновлена! (Обновлено хэдеров: {updated_headers_count})")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка при обращении к API Remnawave: {e}")
        if e.response is not None:
            logger.error(f"Ответ сервера: {e.response.text}")


if __name__ == "__main__":
    if not API_TOKEN:
        logger.error("КРИТИЧЕСКАЯ ОШИБКА: API_TOKEN не задан в .env!")
        exit(1)

    logger.info(f"Сервис запущен. Интервал: {UPDATE_INTERVAL} сек. | API: {PANEL_URL}")
    while True:
        update_routing()
        logger.info(f"Ожидание {UPDATE_INTERVAL} секунд...\n")
        time.sleep(UPDATE_INTERVAL)
