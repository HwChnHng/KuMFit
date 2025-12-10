import types

import pytest

from api_gateway import main as app_module


@pytest.fixture(autouse=True)
def clear_sessions():
    app_module.SESSIONS.clear()
    yield
    app_module.SESSIONS.clear()


def _auth_header(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_sync_everytime_requires_auth():
    client = app_module.app.test_client()
    resp = client.post("/sync/everytime", json={})
    assert resp.status_code == 401


def test_sync_everytime_with_valid_token(monkeypatch):
    client = app_module.app.test_client()
    token = "t1"
    app_module.SESSIONS[token] = "111"

    called = {}

    def fake_trigger(student_id, timetable_url=None):
        called["student_id"] = student_id
        called["timetable_url"] = timetable_url

    monkeypatch.setattr(app_module.gateway_interface, "trigger_sync", fake_trigger)

    resp = client.post("/sync/everytime", json={"timetableUrl": "url"}, headers=_auth_header(token))
    assert resp.status_code == 200
    assert called["student_id"] == "111"
    assert called["timetable_url"] == "url"


def test_recommendations_forbidden_when_student_mismatch():
    client = app_module.app.test_client()
    token = "t2"
    app_module.SESSIONS[token] = "111"
    resp = client.get("/recommendations/222", headers=_auth_header(token))
    assert resp.status_code == 403


def test_recommendations_ok_returns_list(monkeypatch):
    client = app_module.app.test_client()
    token = "t3"
    app_module.SESSIONS[token] = "111"

    dummy_rec = types.SimpleNamespace(result_json=[{"title": "rec"}], created_at=None)
    monkeypatch.setattr(app_module.gateway_interface, "get_recommendation", lambda student_id: dummy_rec)

    resp = client.get("/recommendations/111", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert data[0]["title"] == "rec"


def test_delete_user_requires_auth():
    client = app_module.app.test_client()
    resp = client.delete("/users/111")
    assert resp.status_code == 401


def test_delete_user_forbidden_when_mismatch():
    client = app_module.app.test_client()
    token = "t4"
    app_module.SESSIONS[token] = "111"
    resp = client.delete("/users/222", headers=_auth_header(token))
    assert resp.status_code == 403


def test_delete_user_ok(monkeypatch):
    client = app_module.app.test_client()
    token = "t5"
    app_module.SESSIONS[token] = "111"

    called = {}

    def fake_delete(db, student_id):
        called["sid"] = student_id
        return True

    monkeypatch.setattr(app_module.crud, "delete_user", fake_delete)

    resp = client.delete("/users/111", headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.get_json().get("deleted") is True
    assert called["sid"] == "111"


def test_login_rejects_name_mismatch(monkeypatch):
    client = app_module.app.test_client()

    def fake_get_user(db, student_id):
        return types.SimpleNamespace(student_id=student_id, name="original", password_hash=None)

    monkeypatch.setattr(app_module.crud, "get_user_by_id", fake_get_user)
    monkeypatch.setattr(app_module.crud, "create_user", lambda *args, **kwargs: None)

    resp = client.post("/login", json={"studentId": "111", "name": "other"})
    assert resp.status_code == 400


def test_login_rejects_wrong_password(monkeypatch):
    client = app_module.app.test_client()

    def fake_get_user(db, student_id):
        return types.SimpleNamespace(student_id=student_id, name="user", password_hash=app_module.hash_password("pw"))

    monkeypatch.setattr(app_module.crud, "get_user_by_id", fake_get_user)
    monkeypatch.setattr(app_module.crud, "create_user", lambda *args, **kwargs: None)

    resp = client.post("/login", json={"studentId": "111", "name": "user", "password": "wrong"})
    assert resp.status_code == 401


def test_login_accepts_existing_with_correct_password(monkeypatch):
    client = app_module.app.test_client()

    def fake_get_user(db, student_id):
        return types.SimpleNamespace(student_id=student_id, name="user", password_hash=app_module.hash_password("pw"))

    monkeypatch.setattr(app_module.crud, "get_user_by_id", fake_get_user)
    monkeypatch.setattr(app_module.crud, "create_user", lambda *args, **kwargs: None)

    resp = client.post("/login", json={"studentId": "111", "name": "user", "password": "pw"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "token" in data
