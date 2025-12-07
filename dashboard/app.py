from flask import Flask, render_template, request

app = Flask(__name__)

@app.route("/")
def index():
    # 나중에 DB 붙이기 전까지는 더미 데이터로 테스트
    sample_recommendations = [
        {"title": "자기소개서 클리닉", "category": "취창업비교과", "status": "신청가능", "category_key": "emplym"},
        {"title": "파이썬 기초 스터디", "category": "일반비교과", "status": "대기신청", "category_key": "genl"},
        {"title": "단과대 비교과 특강", "category": "단과대비교과", "status": "신청가능", "category_key": "grup"},
    ]

    sample_wein = [
    {
        "title": "그린봉사단 모집",
        "status": "신청가능",
        "apply_period": "2025.09.01 ~ 2025.09.30",
    },
    {
        "title": "AI 기반 직무 멘토링",
        "status": "대기신청",
        "apply_period": "2025.10.05 ~ 2025.10.20",
    },
]


    # 쿼리스트링에서 category 값 가져오기 (예: ?category=genl)
    current_category = request.args.get("category", "all")

    # 필터링
    if current_category == "all":
        filtered_reco = sample_recommendations
    else:
        filtered_reco = [
            item for item in sample_recommendations
            if item["category_key"] == current_category
        ]

    return render_template(
        "index.html",
        recommendations=filtered_reco,
        wein_programs=sample_wein,
        current_category=current_category,
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
