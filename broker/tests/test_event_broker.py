from unittest import mock

from broker.event_broker import EventBroker


class FakeChannel:
    def __init__(self):
        self.declared = []
        self.published = []

    def queue_declare(self, queue, durable=False, arguments=None):
        self.declared.append({"queue": queue, "durable": durable, "arguments": arguments or {}})

    def basic_publish(self, exchange, routing_key, body, properties=None):
        self.published.append({"exchange": exchange, "routing_key": routing_key, "body": body, "properties": properties})


class FakeConnection:
    def __init__(self, channel):
        self._channel = channel
        self.is_closed = False

    def channel(self):
        return self._channel

    def close(self):
        self.is_closed = True


def test_event_broker_declares_queue_with_dlq():
    fake_channel = FakeChannel()
    fake_conn = FakeConnection(fake_channel)

    with mock.patch("broker.event_broker.pika.BlockingConnection", return_value=fake_conn):
        broker = EventBroker(queue_name="test_queue")

    names = {d["queue"] for d in fake_channel.declared}
    assert "test_queue.dlq" in names
    assert "test_queue" in names

    # 주 큐 선언에 DLQ 옵션이 포함되어야 한다.
    main_decl = next(d for d in fake_channel.declared if d["queue"] == "test_queue")
    assert main_decl["arguments"].get("x-dead-letter-routing-key") == "test_queue.dlq"


def test_event_broker_publish_sends_message():
    fake_channel = FakeChannel()
    fake_conn = FakeConnection(fake_channel)
    with mock.patch("broker.event_broker.pika.BlockingConnection", return_value=fake_conn):
        broker = EventBroker(queue_name="publish_queue")
        broker.publish({"title": "hi"})

    assert fake_channel.published
    msg = fake_channel.published[0]
    assert msg["routing_key"] == "publish_queue"
    assert "hi" in msg["body"]


def test_event_broker_close_closes_connection():
    fake_channel = FakeChannel()
    fake_conn = FakeConnection(fake_channel)
    with mock.patch("broker.event_broker.pika.BlockingConnection", return_value=fake_conn):
        broker = EventBroker(queue_name="q")
        broker.close()
    assert fake_conn.is_closed is True


def test_event_broker_custom_queue_name():
    fake_channel = FakeChannel()
    fake_conn = FakeConnection(fake_channel)
    with mock.patch("broker.event_broker.pika.BlockingConnection", return_value=fake_conn):
        broker = EventBroker(queue_name="custom")
    names = {d["queue"] for d in fake_channel.declared}
    assert "custom" in names
    assert "custom.dlq" in names


def test_event_broker_reconnects_on_failure(monkeypatch):
    fake_channel = FakeChannel()
    fake_conn = FakeConnection(fake_channel)
    calls = {"count": 0}

    def fake_blocking_connection(params):
        calls["count"] += 1
        if calls["count"] == 1:
            raise Exception("fail")
        return fake_conn

    monkeypatch.setattr("broker.event_broker.pika.BlockingConnection", fake_blocking_connection)
    broker = EventBroker(queue_name="retryq")
    assert calls["count"] == 2
    assert broker.channel is fake_channel
