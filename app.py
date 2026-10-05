from flask import Flask, jsonify, request
import os
import requests

app = Flask(__name__)

RIA_API_KEY = os.environ.get("RIA_API_KEY")


@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "service": "AutoScout"
    })


@app.route("/api/search")
def search_cars():
    if not RIA_API_KEY:
        return jsonify({
            "status": "error",
            "message": "RIA_API_KEY не знайдено"
        }), 500

    mark = request.args.get("mark", "9")
    model = request.args.get("model")
    year_from = request.args.get("year_from")
    year_to = request.args.get("year_to")
    price_from = request.args.get("price_from")
    price_to = request.args.get("price_to")

    url = "https://developers.ria.com/auto/search"

    params = {
        "api_key": RIA_API_KEY,
        "category_id": 1,
        "marka_id[0]": mark,
        "countpage": 20,
        "page": 0
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

    try:
        response = requests.get(url, params=params, timeout=15)
        data = response.json()

        return jsonify({
            "status": "ok" if response.ok else "error",
            "ria_status": response.status_code,
            "data": data
        }), response.status_code

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
