# ---------------------------------------------------------
# 사용 예시
# ---------------------------------------------------------

# # app.py 예시
# from models import SessionLocal, User

# # 1. DB 세션 열기
# db = SessionLocal()

# # 2. 데이터 조회
# users = db.query(User).all()

# # 3. 데이터 추가
# new_user = User(student_id="20230001", name="홍길동")
# db.add(new_user)
# db.commit()

# # 4. 세션 닫기 (필수)
# db.close()
# ---------------------------------------------------------


from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = "mysql+pymysql://root:root@db:3306/kumfit"

# 1. 엔진 생성 (DB와 연결하는 핵심 객체)
# echo=True 옵션: 실행되는 SQL 쿼리를 로그에 출력 (디버깅용, 배포시 False)
engine = create_engine(DATABASE_URL, echo=True)

# 2. 세션 공장 생성 (데이터를 넣고 뺄 때 사용하는 '세션'을 찍어내는 공장)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. 모델의 기본 클래스 생성
Base = declarative_base()


# ---------------------------------------------------------
# 1. 사용자 정보 (User)
# ---------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    student_id = Column(String(20), primary_key=True)  # 학번 (로그인 ID)
    name = Column(String(50), nullable=False)  # 이름
    password_hash = Column(String(128))  # 비밀번호 해시
    last_synced_at = Column(DateTime, nullable=True)  # 마지막 동기화 시간

    # 관계 설정 (1:N, 1:1)
    # cascade 옵션: 유저 삭제 시 시간표와 추천 결과도 같이 삭제됨
    timetables = relationship(
        "TimeTable", back_populates="user", cascade="all, delete-orphan"
    )
    recommendation = relationship(
        "Recommendation",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<User {self.student_id} ({self.name})>"


# ---------------------------------------------------------
# 2. 에브리타임 시간표 (TimeTable)
# ---------------------------------------------------------
class TimeTable(Base):
    __tablename__ = "timetables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(20), ForeignKey("users.student_id"), nullable=False)

    day = Column(String(10), nullable=False)  # 요일 (Mon, Tue)
    start_time = Column(String(5), nullable=False)  # 시작 시간 (09:00)
    end_time = Column(String(5), nullable=False)  # 종료 시간 (10:30)
    subject_name = Column(String(100))  # 과목명
    classroom = Column(String(50))  # 강의실

    user = relationship("User", back_populates="timetables")


# ---------------------------------------------------------
# 3. 위인전 비교과 프로그램 (Program)
# ---------------------------------------------------------
class Program(Base):
    __tablename__ = "programs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    title = Column(String(200), nullable=False)  # 과정명
    topic = Column(String(50))  # 비교과주제

    apply_start = Column(DateTime, nullable=True)  # 신청 시작일
    apply_end = Column(DateTime, nullable=True)  # 신청 마감일

    run_time_text = Column(String(200))  # 운영 일시 (Raw Text)

    location = Column(String(100))  # 장소
    target_audience = Column(String(200))  # 대상자 (1학년, 2학년)

    mileage = Column(Integer, default=0)  # 마일리지
    detail_url = Column(String(500))  # 상세 URL

    def __repr__(self):
        return f"<Program {self.title} ({self.topic})>"


# ---------------------------------------------------------
# 4. 추천 결과 (Recommendation)
# ---------------------------------------------------------
class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(20), ForeignKey("users.student_id"), nullable=False)

    result_json = Column(JSON, nullable=False)  # 추천 결과 리스트 (JSON)

    created_at = Column(DateTime, default=datetime.now)  # 생성 일시

    user = relationship("User", back_populates="recommendation")


# 테이블 생성 코드
try:
    Base.metadata.create_all(bind=engine)
    print("데이터베이스 테이블 생성 완료 (또는 이미 존재함)")
except Exception as e:
    print("데이터베이스 연결 실패 (아직 DB가 켜지는 중일 수 있습니다):", e)
