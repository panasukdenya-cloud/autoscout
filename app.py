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


@app.route("/api/test-ria")
def test_ria():
    if not RIA_API_KEY:
        return jsonify({
            "status": "error",
            "message": "RIA_API_KEY не знайдено"
        }), 500

    url = "https://developers.ria.com/auto/categories/"
    
    try:
        response = requests.get(
            url,
            params={"api_key": RIA_API_KEY},
            timeout=15
        )

        return jsonify({
            "status": "ok" if response.ok else "error",
            "ria_status": response.status_code,
            "data": response.json()
        }), response.status_code

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
