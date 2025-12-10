from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

# database.py에서 Base를 가져옵니다.
from .database import Base


# ---------------------------------------------------------
# 1. 사용자 정보 (User)
# ---------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    student_id = Column(String(20), primary_key=True)
    name = Column(String(50), nullable=False)
    password_hash = Column(String(128), nullable=False)
    last_synced_at = Column(DateTime, nullable=True)

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
    day = Column(String(10), nullable=False)
    start_time = Column(String(5), nullable=False)
    end_time = Column(String(5), nullable=False)
    subject_name = Column(String(100))
    classroom = Column(String(50))

    user = relationship("User", back_populates="timetables")


# ---------------------------------------------------------
# 3. 위인전 비교과 프로그램 (Program)
# ---------------------------------------------------------
class Program(Base):
    __tablename__ = "programs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    topic = Column(String(50))
    apply_start = Column(DateTime, nullable=True)
    apply_end = Column(DateTime, nullable=True)
    run_time_text = Column(String(200))
    location = Column(String(100))
    target_audience = Column(String(200))
    mileage = Column(Integer, default=0)
    detail_url = Column(String(500))
    updated_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<Program {self.title} ({self.topic})>"


# ---------------------------------------------------------
# 4. 추천 결과 (Recommendation)
# ---------------------------------------------------------
class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(20), ForeignKey("users.student_id"), nullable=False)
    result_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="recommendation")
