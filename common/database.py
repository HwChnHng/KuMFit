from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

# Docker Compose 내부 통신용 URL (utf8mb4로 고정)
DATABASE_URL = "mysql+pymysql://root:root@db:3306/kumfit?charset=utf8mb4"

# 1. 엔진 생성
engine = create_engine(DATABASE_URL, echo=True)

# 2. 세션 공장 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. 모델의 조상 클래스 (Base) 생성
# models.py에서 이 Base를 상속받아 클래스를 만들게 됩니다.
Base = declarative_base()


# 4. DB 세션 생성 및 종료를 관리하는 헬퍼 함수 (Context Manager 패턴)
# @contextmanager 데코레이터 [추가]
@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# DB 테이블을 생성하는 함수.
def init_db():
    import common.models

    try:
        Base.metadata.create_all(bind=engine)
        print("[DB] 테이블 초기화 완료")
    except OperationalError as e:
        # 다른 서비스가 이미 생성한 경우 1050 에러가 날 수 있음 -> 무시
        if getattr(e.orig, "args", []) and e.orig.args[0] == 1050:
            print("[DB] 테이블 이미 존재함, 생성 건너뜀")
        else:
            raise
