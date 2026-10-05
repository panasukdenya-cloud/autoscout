from flask import Flask, jsonify, request
import os
import requests

app = Flask(__name__)

RIA_API_KEY = os.environ.get("RIA_API_KEY")
RIA_BASE = "https://developers.ria.com"


def ria_get(path, params=None):
    params = params or {}
    params["api_key"] = RIA_API_KEY

    response = requests.get(
        f"{RIA_BASE}{path}",
        params=params,
        timeout=20
    )
    response.raise_for_status()
    return response.json()


@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "service": "AutoScout"
    })


@app.route("/api/search")
def search():
    if not RIA_API_KEY:
        return jsonify({
            "status": "error",
            "message": "RIA_API_KEY not found"
        }), 500

    mark = request.args.get("mark")
    model = request.args.get("model")

    year_from = request.args.get("year_from")
    year_to = request.args.get("year_to")

    price_from = request.args.get("price_from")
    price_to = request.args.get("price_to")

    region = request.args.get("region")

    below = request.args.get("below", "15", type=float)
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

        result = data.get("result", {})
        search_result = result.get("search_result", {})

        ids = search_result.get("ids", [])
        total = search_result.get("count", 0)

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
            "page": page,
            "per_page": 20,
            "total_found": total,
            "ids": ids,
            "next_page": page + 1 if ids else None
        })

    except requests.RequestException as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/api/car/<auto_id>")
def car(auto_id):
    if not RIA_API_KEY:
        return jsonify({
            "status": "error",
            "message": "RIA_API_KEY not found"
        }), 500

    try:
        info = ria_get(
            "/auto/info",
            {"auto_id": auto_id}
        )

        return jsonify({
            "status": "ok",
            "car": {
                "id": auto_id,
                "title": info.get("title"),
                "price_usd": info.get("USD"),
                "year": info.get("autoData", {}).get("year"),
                "race": info.get("autoData", {}).get("race"),
                "city": info.get("locationCityName"),
                "photo": info.get("photoData", {}).get("seoLinkM"),
                "link": info.get("linkToView")
            }
        })

    except requests.RequestException as e:
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
