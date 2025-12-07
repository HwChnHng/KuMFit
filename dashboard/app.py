import os
from flask import Flask, render_template, request

app = Flask(__name__)

# API 게이트웨이 주소 (env로 오버라이드 가능)
API_BASE = os.getenv("API_BASE", "http://localhost:5000")


@app.route("/")
def index():
    return render_template(
        "index.html",
        current_category=request.args.get("category", "all"),
        api_base=API_BASE,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
