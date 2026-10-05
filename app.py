from flask import Flask, jsonify, request
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

RIA_API_KEY = os.environ.get("RIA_API_KEY")
RIA_BASE = "https://developers.ria.com"

# Кеш ринкових цін — 30 хвилин
MARKET_CACHE = {}
MARKET_CACHE_TTL = 1800


@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


def ria_get(path, params=None):
    if not RIA_API_KEY:
        raise RuntimeError("RIA_API_KEY not found")

    params = params or {}
    params["api_key"] = RIA_API_KEY

    r = requests.get(
        RIA_BASE + path,
        params=params,
        timeout=30
    )

    r.raise_for_status()
    return r.json()


def get_car(auto_id):
    info = ria_get(
        "/auto/info",
        {"auto_id": auto_id}
    )

    auto_data = info.get("autoData", {})

    link = info.get("linkToView")
    if link and link.startswith("/"):
        link = "https://auto.ria.com" + link

    return {
        "id": str(auto_id),

        "title": info.get("title"),

        "mark": info.get("markName"),
        "mark_id": info.get("markId"),

        "model": info.get("modelName"),
        "model_id": info.get("modelId"),

        "year": auto_data.get("year"),

        "price_usd": info.get("USD"),

        "race": auto_data.get("race"),
        "race_int": auto_data.get("raceInt"),

        "fuel": auto_data.get("fuelName"),
        "gearbox": auto_data.get("gearboxName"),

        "city": info.get("locationCityName"),

        "photo": (
            info.get("photoData", {})
            .get("seoLinkM")
        ),

        "link": link
    }


def get_market_price(mark_id, model_id, year):
    key = f"{mark_id}:{model_id}:{year}"

    cached = MARKET_CACHE.get(key)

    if cached:
        if time.time() - cached["time"] < MARKET_CACHE_TTL:
            return cached["data"]

    data = ria_get(
        "/auto/average_price",
        {
            "marka_id": mark_id,
            "model_id": model_id,
            "yers": year
        }
    )

    percentiles = data.get("percentiles", {})

    median = (
        percentiles.get("50.0")
        or percentiles.get("50")
        or percentiles.get(50)
        or percentiles.get(50.0)
    )

    result = {
        "median": median,
        "average": data.get("arithmeticMean"),
        "interquartile": data.get("interQuartileMean"),
        "total": data.get("total")
    }

    MARKET_CACHE[key] = {
        "time": time.time(),
        "data": result
    }

    return result


@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "service": "AutoScout"
    })


@app.route("/api/car/<auto_id>")
def car(auto_id):
    try:
        return jsonify({
            "status": "ok",
            "car": get_car(auto_id)
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/api/deals")
def deals():

    # НЕОБОВ'ЯЗКОВІ
    mark = request.args.get("mark")
    model = request.args.get("model")

    year_from = request.args.get("year_from")
    year_to = request.args.get("year_to")

    price_from = request.args.get("price_from")
    price_to = request.args.get("price_to")

    region = request.args.get("region")

    # Наприклад 15 = мінімум 15% нижче ринку
    below = request.args.get(
        "below",
        15,
        type=float
    )

    page = request.args.get(
        "page",
        0,
        type=int
    )

    limit = request.args.get(
        "limit",
        20,
        type=int
    )

    limit = max(1, min(limit, 20))

    params = {
        "category_id": 1,
        "countpage": limit,
        "page": page
    }

    # Якщо марка обрана
    if mark:
        params["marka_id[0]"] = mark

    # Якщо модель обрана
    if model:
        params["model_id[0]"] = model

    if year_from:
        params["s_yers[0]"] = year_from

    if year_to:
        params["po_yers[0]"] = year_to

    if price_from:
        params["price_ot"] = price_from

    if price_to:
        params["price_do"] = price_to

    if region:
        params["state[0]"] = region

    try:

        search_data = ria_get(
            "/auto/search",
            params
        )

        search_result = (
            search_data
            .get("result", {})
            .get("search_result", {})
        )

        ids = search_result.get(
            "ids",
            []
        )[:limit]

        cars = []

        # Отримуємо дані оголошень паралельно
        with ThreadPoolExecutor(max_workers=8) as executor:

            futures = [
                executor.submit(
                    get_car,
                    auto_id
                )
                for auto_id in ids
            ]

            for future in as_completed(futures):

                try:
                    car_data = future.result()
                    cars.append(car_data)
                except Exception:
                    pass

        deals_found = []

        for car in cars:

            mark_id = car.get("mark_id")
            model_id = car.get("model_id")
            year = car.get("year")
            price = car.get("price_usd")

            if not all([
                mark_id,
                model_id,
                year,
                price
            ]):
                continue

            try:
                market = get_market_price(
                    mark_id,
                    model_id,
                    year
                )
            except Exception:
                continue

            market_price = market.get("median")

            if not market_price:
                continue

            try:
                price = float(price)
                market_price = float(market_price)
            except (ValueError, TypeError):
                continue

            if market_price <= 0:
                continue

            discount = (
                (market_price - price)
                / market_price
            ) * 100

            discount = round(
                discount,
                1
            )

            if discount < below:
                continue

            car["market_price"] = round(
                market_price
            )

            car["below_market_percent"] = discount

            car["market_ads_count"] = market.get(
                "total"
            )

            deals_found.append(car)

        # Найвигідніші зверху
        deals_found.sort(
            key=lambda x:
            x["below_market_percent"],
            reverse=True
        )

        return jsonify({

            "status": "ok",

            "mode": (
                "selected_car"
                if mark or model
                else "all_cars"
            ),

            "filters": {
                "mark": mark,
                "model": model,
                "year_from": year_from,
                "year_to": year_to,
                "price_from": price_from,
                "price_to": price_to,
                "region": region,
                "below_percent": below
            },

            "total_found_ria":
                search_result.get("count", 0),

            "checked":
                len(cars),

            "deals_found":
                len(deals_found),

            "deals":
                deals_found,

            "page":
                page,

            "next_page":
                page + 1 if ids else None
        })

    except Exception as e:

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/routes")
def routes():
    return jsonify(
        [str(x) for x in app.url_map.iter_rules()]
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                10000
            )
        )
    )
