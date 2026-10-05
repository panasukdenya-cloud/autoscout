from flask import Flask, jsonify, request
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

RIA_API_KEY = os.environ.get("RIA_API_KEY")
RIA_USER_ID = os.environ.get("RIA_USER_ID")
RIA_BASE = "https://developers.ria.com"

# Кеш ринкової ціни, щоб не витрачати зайві запити
MARKET_CACHE = {}
MARKET_CACHE_SECONDS = 15 * 60


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


def ria_get(path, params=None):
    if not RIA_API_KEY:
        raise RuntimeError("RIA_API_KEY not found")

    params = params or {}
    params["api_key"] = RIA_API_KEY

    response = requests.get(
        f"{RIA_BASE}{path}",
        params=params,
        timeout=25
    )

    response.raise_for_status()
    return response.json()


def get_car_info(auto_id):
    info = ria_get(
        "/auto/info",
        {"auto_id": auto_id}
    )

    link = info.get("linkToView")

    if link and link.startswith("/"):
        link = "https://auto.ria.com" + link

    return {
        "id": str(auto_id),
        "title": info.get("title"),
        "price_usd": info.get("USD"),
        "year": info.get("autoData", {}).get("year"),
        "race": info.get("autoData", {}).get("race"),
        "city": info.get("locationCityName"),
        "photo": info.get("photoData", {}).get("seoLinkM"),
        "link": link
    }


def get_market_price(mark, model, year):
    cache_key = f"{mark}:{model}:{year}"

    cached = MARKET_CACHE.get(cache_key)

    if cached:
        age = time.time() - cached["time"]

        if age < MARKET_CACHE_SECONDS:
            return cached["data"]

    params = {
        "marka_id": mark,
        "model_id": model,
        "yers": year
    }

    data = ria_get(
        "/auto/average_price",
        params
    )

    percentiles = data.get("percentiles", {})

    median = (
        percentiles.get("50.0")
        or percentiles.get(50.0)
        or percentiles.get("50")
    )

    result = {
        "median": median,
        "average": data.get("arithmeticMean"),
        "interquartile_average": data.get("interQuartileMean"),
        "sample_size": data.get("total")
    }

    MARKET_CACHE[cache_key] = {
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


@app.route("/api/search")
def search():
    mark = request.args.get("mark")
    model = request.args.get("model")

    year_from = request.args.get("year_from")
    year_to = request.args.get("year_to")

    price_from = request.args.get("price_from")
    price_to = request.args.get("price_to")

    region = request.args.get("region")

    page = request.args.get("page", 0, type=int)

    if not mark:
        return jsonify({
            "status": "error",
            "message": "mark is required"
        }), 400

    params = {
        "category_id": 1,
        "marka_id[0]": mark,
        "countpage": 20,
        "page": page
    }

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
        data = ria_get("/auto/search", params)

        search_result = (
            data.get("result", {})
            .get("search_result", {})
        )

        ids = search_result.get("ids", [])

        return jsonify({
            "status": "ok",
            "ids": ids,
            "total_found": search_result.get("count", 0),
            "page": page,
            "per_page": 20,
            "next_page": page + 1 if ids else None
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/api/car/<auto_id>")
def car(auto_id):
    try:
        return jsonify({
            "status": "ok",
            "car": get_car_info(auto_id)
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/api/market")
def market():
    mark = request.args.get("mark")
    model = request.args.get("model")
    year = request.args.get("year")

    if not mark or not model or not year:
        return jsonify({
            "status": "error",
            "message": "mark, model and year are required"
        }), 400

    try:
        market_data = get_market_price(
            mark,
            model,
            year
        )

        return jsonify({
            "status": "ok",
            "market": market_data
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/api/deals")
def deals():
    mark = request.args.get("mark")
    model = request.args.get("model")

    year_from = request.args.get("year_from")
    year_to = request.args.get("year_to")

    price_from = request.args.get("price_from")
    price_to = request.args.get("price_to")

    region = request.args.get("region")

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

    if not mark or not model:
        return jsonify({
            "status": "error",
            "message": "mark and model are required"
        }), 400

    search_params = {
        "category_id": 1,
        "marka_id[0]": mark,
        "model_id[0]": model,
        "countpage": limit,
        "page": page
    }

    if year_from:
        search_params["s_yers[0]"] = year_from

    if year_to:
        search_params["po_yers[0]"] = year_to

    if price_from:
        search_params["price_ot"] = price_from

    if price_to:
        search_params["price_do"] = price_to

    if region:
        search_params["state[0]"] = region

    try:
        search_data = ria_get(
            "/auto/search",
            search_params
        )

        search_result = (
            search_data.get("result", {})
            .get("search_result", {})
        )

        ids = search_result.get("ids", [])[:limit]

        cars = []

        # Отримуємо дані авто паралельно — значно швидше
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(get_car_info, auto_id): auto_id
                for auto_id in ids
            }

            for future in as_completed(futures):
                try:
                    cars.append(future.result())
                except Exception:
                    pass

        deals_list = []

        for car in cars:
            price = car.get("price_usd")
            year = car.get("year")

            if not price or not year:
                continue

            try:
                market_data = get_market_price(
                    mark,
                    model,
                    year
                )
            except Exception:
                continue

            market_price = market_data.get("median")

            if not market_price:
                continue

            try:
                price = float(price)
                market_price = float(market_price)
            except (TypeError, ValueError):
                continue

            if market_price <= 0:
                continue

            discount = (
                (market_price - price)
                / market_price
                * 100
            )

            discount = round(discount, 1)

            if discount < below:
                continue

            car["market_price"] = round(market_price)
            car["below_market_percent"] = discount
            car["market_sample_size"] = market_data.get(
                "sample_size"
            )

            deals_list.append(car)

        deals_list.sort(
            key=lambda x: x["below_market_percent"],
            reverse=True
        )

        return jsonify({
            "status": "ok",
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
            "total_found_ria": search_result.get(
                "count",
                0
            ),
            "checked": len(cars),
            "deals_found": len(deals_list),
            "deals": deals_list,
            "page": page,
            "next_page": page + 1 if ids else None
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/routes")
def routes():
    return jsonify(
        [str(rule) for rule in app.url_map.iter_rules()]
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
