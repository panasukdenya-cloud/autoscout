import os
import time
import requests

from app import ria_get, get_car, get_market_price

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Адреса нашого backend
SETTINGS_URL = "https://autoscout-4ojj.onrender.com/api/monitor-settings"

# Перевірка кожні 5 хвилин
CHECK_EVERY_SECONDS = 300

seen_ids = set()


def get_settings():
    r = requests.get(SETTINGS_URL, timeout=20)
    r.raise_for_status()

    data = r.json()
    return data.get("settings", {})


def send_telegram(car, market_price, discount):
    text = (
        f"🔥 <b>{car.get('title', 'Авто')}</b>\n\n"
        f"💵 Ціна: <b>${int(float(car['price_usd'])):,}</b>\n"
        f"📊 Ринок: <b>${int(float(market_price)):,}</b>\n"
        f"🔥 Нижче ринку: <b>−{discount}%</b>\n\n"
        f"📅 Рік: {car.get('year', '-')}\n"
        f"🛣 Пробіг: {car.get('race', '-')}\n"
        f"📍 {car.get('city', '-')}\n\n"
        f"🔗 {car.get('link', '')}"
    )

    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        },
        timeout=20
    )

    r.raise_for_status()


def get_latest_ids(settings):
    params = {
        "category_id": 1,
        "countpage": 20,
        "page": 0
    }

    year_from = settings.get("year_from")
    year_to = settings.get("year_to")
    region = settings.get("region")
    mark = settings.get("mark")
    model = settings.get("model")

    if year_from:
        params["s_yers[0]"] = year_from

    if year_to:
        params["po_yers[0]"] = year_to

    if region:
        params["state[0]"] = region

    if mark:
        params["marka_id[0]"] = mark

    if model:
        params["model_id[0]"] = model

    data = ria_get("/auto/search", params)

    return (
        data.get("result", {})
        .get("search_result", {})
        .get("ids", [])
    )


def check_cars():
    global seen_ids

    settings = get_settings()

    if not settings.get("enabled", True):
        print("Monitoring disabled")
        return

    below = float(settings.get("below", 20))

    ids = get_latest_ids(settings)

    # При першому запуску запам'ятовуємо існуючі оголошення.
    # Старими авто Telegram не засипаємо.
    if not seen_ids:
        seen_ids.update(ids)
        print(f"Started. Remembered {len(ids)} ads.")
        return

    new_ids = [
        auto_id
        for auto_id in ids
        if auto_id not in seen_ids
    ]

    print(f"New ads: {len(new_ids)}")

    for auto_id in new_ids:
        seen_ids.add(auto_id)

        try:
            car = get_car(auto_id)

            mark_id = car.get("mark_id")
            model_id = car.get("model_id")
            year = car.get("year")
            price = car.get("price_usd")

            if not all([mark_id, model_id, year, price]):
                continue

            market = get_market_price(
                mark_id,
                model_id,
                year
            )

            market_price = market.get("median")

            if not market_price:
                continue

            price = float(price)
            market_price = float(market_price)

            if market_price <= 0:
                continue

            discount = round(
                ((market_price - price) / market_price) * 100,
                1
            )

            if discount >= below:
                send_telegram(
                    car,
                    market_price,
                    discount
                )

                print(
                    f"SENT {car.get('title')} -{discount}%"
                )

        except Exception as e:
            print(f"ERROR {auto_id}: {e}")


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID missing")

    print("AutoScout monitor started")

    while True:
        try:
            check_cars()
        except Exception as e:
            print(f"MONITOR ERROR: {e}")

        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
