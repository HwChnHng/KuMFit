import sys
import os
from flask import Flask, render_template, request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 현재 위치(dashboard)의 부모 폴더(KuMFit)를 path에 추가
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from common.models import Program

# --- [DB 설정] ---
# docker-compose로 띄운 DB 포트가 3306으로 열려있으므로 접속 가능합니다.
DATABASE_URL = "mysql+pymysql://root:root@localhost:3306/kumfit"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = Flask(__name__)

@app.route("/")
def index():
    # 1. DB 세션 열기
    db = SessionLocal()
    
    try:
        # 2. DB에서 '위인전 프로그램' 진짜 데이터 가져오기 (최신순)
        # Consumer가 열심히 저장해둔 데이터를 여기서 꺼냄
        real_programs = db.query(Program).order_by(Program.id.desc()).all()
        
        # 3. 템플릿에 보낼 형태로 변환
        wein_data = []
        for p in real_programs:
            wein_data.append({
                "title": p.title,
                # DB 모델에 status 컬럼이 없다면 크롤러가 title이나 다른 곳에 넣었는지 확인 필요
                # 일단은 '접수중'으로 표시하거나, 필요한 경우 models.py 수정 필요
                "status": "접수중", 
                "apply_period": p.apply_start.strftime('%Y-%m-%d') if p.apply_start else "-"
            })
            
    except Exception as e:
        print(f"[Error] DB 조회 실패: {e}")
        wein_data = [] # 에러 나면 빈 리스트
    finally:
        db.close()

    # --- [추천 데이터 (아직 더미)] ---
    sample_recommendations = [
        {"title": "자기소개서 클리닉", "category": "취창업비교과", "status": "신청가능", "category_key": "emplym"},
        {"title": "파이썬 기초 스터디", "category": "일반비교과", "status": "대기신청", "category_key": "genl"},
    ]

    current_category = request.args.get("category", "all")
    if current_category == "all":
        filtered_reco = sample_recommendations
    else:
        filtered_reco = [item for item in sample_recommendations if item["category_key"] == current_category]

    return render_template(
        "index.html",
        recommendations=filtered_reco,
        wein_programs=wein_data, 
        current_category=current_category,
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)