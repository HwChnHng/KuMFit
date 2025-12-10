import hashlib
import os
import secrets
from functools import wraps

from flask import Flask, jsonify, request
from flask_cors import CORS

from broker.event_broker import EventBroker
from common import crud
from common.database import SessionLocal, init_db

app = Flask(__name__)
CORS(app)

# 인메모리 세션 저장소
SESSIONS = {}

# 큐 설정
SYNC_QUEUE = os.getenv("EVERYTIME_QUEUE", "everytime_sync")


def hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip()
        if not token or token not in SESSIONS:
            return jsonify({"error": "unauthorized"}), 401
        request.student_id = SESSIONS[token]
        return fn(*args, **kwargs)

    return wrapper


class LoginInterface:
    def __init__(self, sessions):
        self.sessions = sessions

    def login(self, student_id: str, name: str, password: str = None) -> str:
        with SessionLocal() as db:
            existing = crud.get_user_by_id(db, student_id=student_id)
            if existing:
                # 이름 불일치 시 거절
                if existing.name != name:
                    raise ValueError("name_mismatch")
                # 비밀번호가 저장돼 있다면 검증 필요
                if existing.password_hash:
                    if not password or hash_password(password) != existing.password_hash:
                        raise PermissionError("invalid_password")
                # 비밀번호가 없고 새 비밀번호를 주면 설정
                elif password:
                    existing.password_hash = hash_password(password)
                    db.commit()
            else:
                # 신규 사용자 생성
                password_hash = hash_password(password) if password else None
                crud.create_user(db, student_id=student_id, name=name, password_hash=password_hash)
        token = secrets.token_urlsafe(24)
        self.sessions[token] = student_id
        return token

    def logout(self, token: str):
        self.sessions.pop(token, None)

    def check_session(self, token: str) -> bool:
        return token in self.sessions


class APIGatewayInterface:
    def __init__(self, queue_name: str):
        self.queue_name = queue_name

    def trigger_sync(self, student_id: str, timetable_url: str = None):
        broker = EventBroker(queue_name=self.queue_name)
        payload = {
            "type": "sync_everytime",
            "studentId": student_id,
        }
        if timetable_url:
            payload["timetableUrl"] = timetable_url
        broker.publish(payload)
        broker.close()

    def get_recommendation(self, student_id: str):
        with SessionLocal() as db:
            rec = crud.get_recommendation(db, student_id)
        return rec

    def get_programs(self):
        with SessionLocal() as db:
            programs = crud.get_all_programs(db)
        return programs


login_interface = LoginInterface(SESSIONS)
gateway_interface = APIGatewayInterface(SYNC_QUEUE)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True, silent=True) or {}
    student_id = data.get("studentId") or data.get("student_id")
    name = data.get("name")
    password = data.get("password")
    if not student_id or not name:
        return jsonify({"error": "studentId and name required"}), 400

    try:
        token = login_interface.login(student_id, name, password)
        return jsonify({"token": token, "studentId": student_id})
    except ValueError as e:
        if str(e) == "name_mismatch":
            return jsonify({"error": "name mismatch"}), 400
        raise
    except PermissionError:
        return jsonify({"error": "invalid credentials"}), 401


@app.route("/logout", methods=["POST"])
@require_auth
def logout():
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    login_interface.logout(token)
    return jsonify({"message": "logged out"})


@app.route("/session", methods=["GET"])
@require_auth
def session_check():
    return jsonify({"studentId": request.student_id})


@app.route("/sync/everytime", methods=["POST"])
@require_auth
def sync_everytime():
    student_id = request.student_id
    data = request.get_json(silent=True) or {}
    timetable_url = data.get("timetableUrl")
    gateway_interface.trigger_sync(student_id, timetable_url)
    return jsonify({"status": "accepted", "studentId": student_id})


@app.route("/recommendations/<student_id>", methods=["GET"])
@require_auth
def recommendations(student_id):
    if student_id != request.student_id:
        return jsonify({"error": "forbidden"}), 403
    rec = gateway_interface.get_recommendation(student_id)
    data = rec.result_json if rec else []
    return jsonify(data)


@app.route("/users/<student_id>", methods=["DELETE"])
@require_auth
def delete_user(student_id):
    if student_id != request.student_id:
        return jsonify({"error": "forbidden"}), 403
    with SessionLocal() as db:
        ok = crud.delete_user(db, student_id)
    if ok:
        # 세션도 제거
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip()
        login_interface.logout(token)
        return jsonify({"deleted": True})
    return jsonify({"deleted": False, "error": "not found"}), 404


@app.route("/programs", methods=["GET"])
@require_auth
def programs():
    programs = gateway_interface.get_programs()
    serialized = [
        {
            "id": p.id,
            "title": p.title,
            "topic": p.topic,
            "apply_start": p.apply_start.isoformat() if p.apply_start else None,
            "apply_end": p.apply_end.isoformat() if p.apply_end else None,
            "run_time_text": p.run_time_text,
            "location": p.location,
            "target_audience": p.target_audience,
            "mileage": p.mileage,
            "detail_url": p.detail_url,
        }
        for p in programs
    ]
    return jsonify(serialized)


if __name__ == "__main__":
    # 테이블이 없으면 생성
    init_db()
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
