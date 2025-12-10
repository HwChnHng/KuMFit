from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session

# 같은 폴더 내의 models 모듈 임포트
from .models import Program, Recommendation, TimeTable, User


# ---------------------------------------------------------
# 1. 사용자 (User) 관련
# ---------------------------------------------------------
def create_user(db: Session, student_id: str, name: str, password_hash: str = None):
    """
    사용자 신규 생성
    이미 존재하는 경우 생성하지 않고 기존 사용자 정보를 반환합니다.
    """
    user = db.query(User).filter(User.student_id == student_id).first()

    if user:
        # 이미 존재하면 해당 유저 객체 반환 (혹은 에러 발생 처리가 필요하면 수정 가능)
        return user

    # 존재하지 않으면 새로 생성
    user = User(student_id=student_id, name=name, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, student_id: str):
    """
    사용자 삭제
    models.py의 cascade 설정에 의해 연결된 TimeTable, Recommendation도 함께 삭제됩니다.
    """
    user = db.query(User).filter(User.student_id == student_id).first()

    if not user:
        return False  # 삭제할 대상이 없음

    db.delete(user)
    db.commit()
    return True


def get_user_by_id(db: Session, student_id: str):
    """학번으로 사용자 조회"""
    return db.query(User).filter(User.student_id == student_id).first()


# ---------------------------------------------------------
# 2. 시간표 (TimeTable) 관련 - 에브리타임 크롤러용
# ---------------------------------------------------------
def save_timetables(db: Session, student_id: str, timetable_data: List[Dict]):
    """
    기존 시간표를 삭제하고 새로운 시간표 리스트를 저장 (Transaction)
    timetable_data 예시: [{'day': 'Mon', 'start_time': '09:00', ...}, ...]
    """
    try:
        # 1. 기존 시간표 삭제
        db.query(TimeTable).filter(TimeTable.student_id == student_id).delete()

        # 2. 새 시간표 객체 생성 및 추가
        for item in timetable_data:
            tt = TimeTable(
                student_id=student_id,
                day=item["day"],
                start_time=item["start_time"],
                end_time=item["end_time"],
                subject_name=item["subject_name"],
                classroom=item.get("classroom", ""),
            )
            db.add(tt)

        # 3. 유저 동기화 시간 업데이트
        user = db.query(User).filter(User.student_id == student_id).first()
        if user:
            user.last_synced_at = datetime.now()

        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"[CRUD Error] save_timetables: {e}")
        raise e


def get_timetables(db: Session, student_id: str):
    """특정 학생의 시간표 조회"""
    return db.query(TimeTable).filter(TimeTable.student_id == student_id).all()


# ---------------------------------------------------------
# 3. 비교과 프로그램 (Program) 관련 - 위인전 크롤러용
# ---------------------------------------------------------
def save_programs(db: Session, program_data: List[Dict]):
    """전체 비교과 프로그램 목록 갱신"""
    # KST 기준 타임스탬프
    now_kst = datetime.utcnow() + timedelta(hours=9)
    try:
        # 전체 삭제 후 재삽입 (단순 동기화 전략)
        db.query(Program).delete()

        for item in program_data:
            prog = Program(
                title=item["title"],
                topic=item.get("topic"),
                apply_start=item.get("apply_start"),  # datetime 객체여야 함
                apply_end=item.get("apply_end"),
                run_time_text=item.get("run_time_text"),
                location=item.get("location"),
                target_audience=item.get("target_audience"),
                mileage=item.get("mileage", 0),
                detail_url=item.get("detail_url"),
                updated_at=now_kst,
            )
            db.add(prog)

        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"[CRUD Error] save_programs: {e}")
        raise e


def get_all_programs(db: Session):
    """모든 비교과 프로그램 조회"""
    return db.query(Program).all()


# ---------------------------------------------------------
# 4. 추천 결과 (Recommendation) 관련 - Consumer/Gateway용
# ---------------------------------------------------------
def save_recommendation(db: Session, student_id: str, results: List[Dict]):
    """추천 결과(JSON) 저장(Recommendation Consumer)"""
    try:
        # 기존 추천 내역 확인
        rec = (
            db.query(Recommendation)
            .filter(Recommendation.student_id == student_id)
            .first()
        )

        if rec:
            rec.result_json = results
            rec.created_at = datetime.now()
        else:
            rec = Recommendation(student_id=student_id, result_json=results)
            db.add(rec)

        db.commit()
        return rec
    except Exception as e:
        db.rollback()
        print(f"[CRUD Error] save_recommendation: {e}")
        raise e


def get_recommendation(db: Session, student_id: str):
    """학생의 추천 결과 조회(API Gateway)"""
    return (
        db.query(Recommendation).filter(Recommendation.student_id == student_id).first()
    )
