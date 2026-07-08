"""ThreadsService: two-step publish, reply chaining, verify — with a fake session."""
import pytest

from services import threads as threads_module
from services.errors import PartialThreadError
from services.threads import ThreadsService


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} error")

    def json(self):
        return self._payload


class FakeSession:
    """Returns creation ids on /threads and post ids on /threads_publish."""

    def __init__(self):
        self.posts = []   # (url, data) for POSTs
        self.gets = []    # (url, params) for GETs
        self._creation = 0
        self._published = 0

    container_status = "FINISHED"

    def get(self, url, params=None, timeout=None):
        self.gets.append((url, dict(params or {})))
        if (params or {}).get("fields") == "status,error_message":
            return _Resp({"status": self.container_status, "error_message": "boom detail"})
        if url.endswith("/insights"):
            return _Resp({"data": [
                {"name": "views", "values": [{"value": 120}]},
                {"name": "likes", "total_value": {"value": 5}},
                {"name": "replies", "values": [{"value": 2}]},
                {"name": "reposts", "values": [{"value": 1}]},
                {"name": "quotes", "values": [{"value": 0}]},
            ]})
        assert url.endswith("/me")
        return _Resp({"id": "17800000", "username": "ninetypm"})

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, dict(data)))
        if url.endswith("/threads_publish"):
            self._published += 1
            return _Resp({"id": f"90{self._published}"})
        self._creation += 1
        return _Resp({"id": f"C{self._creation}"})


def _svc():
    return ThreadsService(session=FakeSession(), access_token="tok", user_id="17800000")


def test_verify_returns_handle():
    assert _svc().verify() == "ninetypm"


def test_post_post_two_step_publish():
    svc = _svc()
    pid = svc.post_post("hello")
    assert pid == "901"
    create, publish = svc.session.posts
    assert create[0].endswith("/17800000/threads")
    assert create[1]["media_type"] == "TEXT"
    assert create[1]["text"] == "hello"
    assert "reply_to_id" not in create[1]
    assert publish[0].endswith("/17800000/threads_publish")
    assert publish[1]["creation_id"] == "C1"


def test_post_thread_chains_replies():
    svc = _svc()
    ids = svc.post_thread(["one", "two", "three"])
    assert ids == ["901", "902", "903"]
    creates = [d for url, d in svc.session.posts if url.endswith("/threads")]
    assert "reply_to_id" not in creates[0]
    assert creates[1]["reply_to_id"] == "901"
    assert creates[2]["reply_to_id"] == "902"


def test_dry_run_never_touches_network():
    svc = ThreadsService(dry_run=True, access_token="", user_id="")
    ids = svc.post_thread(["a", "b"])
    assert all(i.startswith("DRYRUN-TH-") for i in ids)
    assert svc.session is None


def test_get_insights_maps_views_to_impressions():
    svc = _svc()
    out = svc.get_insights(["901"])
    assert out["901"] == {"impressions": 120, "likes": 5, "replies": 2, "reposts": 1, "quotes": 0}
    url, params = svc.session.gets[0]
    assert url.endswith("/901/insights")
    assert "views" in params["metric"]
    assert params["access_token"] == "tok"


def test_get_insights_survives_per_post_errors():
    class FailingSession(FakeSession):
        def get(self, url, params=None, timeout=None):
            if "/bad/" in url:
                raise RuntimeError("400 permission error")
            return super().get(url, params=params, timeout=timeout)

    svc = ThreadsService(session=FailingSession(), access_token="tok", user_id="17800000")
    out = svc.get_insights(["bad", "901"])
    assert "bad" not in out
    assert out["901"]["impressions"] == 120


def test_publish_retries_transient_500(monkeypatch):
    monkeypatch.setattr(threads_module, "PUBLISH_RETRY_DELAYS", (0.0, 0.0))

    class FlakySession(FakeSession):
        def __init__(self):
            super().__init__()
            self.publish_attempts = 0

        def post(self, url, data=None, timeout=None):
            if url.endswith("/threads_publish"):
                self.publish_attempts += 1
                if self.publish_attempts == 1:
                    resp = _Resp({"id": "never"})
                    resp.status_code = 500
                    return resp
            return super().post(url, data=data, timeout=timeout)

    svc = ThreadsService(session=FlakySession(), access_token="tok", user_id="17800000")
    assert svc.post_post("hello") == "901"
    assert svc.session.publish_attempts == 2


def test_create_container_retries_network_error(monkeypatch):
    monkeypatch.setattr(threads_module, "PUBLISH_RETRY_DELAYS", (0.0, 0.0))

    class FlakyNetwork(FakeSession):
        def __init__(self):
            super().__init__()
            self.create_attempts = 0

        def post(self, url, data=None, timeout=None):
            if url.endswith("/threads"):
                self.create_attempts += 1
                if self.create_attempts == 1:
                    raise ConnectionError("connection reset")
            return super().post(url, data=data, timeout=timeout)

    svc = ThreadsService(session=FlakyNetwork(), access_token="tok", user_id="17800000")
    assert svc.post_post("hello") == "901"
    assert svc.session.create_attempts == 2


def test_post_gives_up_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(threads_module, "PUBLISH_RETRY_DELAYS", (0.0,))

    class AlwaysDown(FakeSession):
        def post(self, url, data=None, timeout=None):
            if url.endswith("/threads"):
                resp = _Resp({})
                resp.status_code = 503
                return resp
            return super().post(url, data=data, timeout=timeout)

    svc = ThreadsService(session=AlwaysDown(), access_token="tok", user_id="17800000")
    with pytest.raises(Exception):
        svc.post_post("hello")


def test_publish_retries_client_error_media_not_ready(monkeypatch):
    # The 400 "Media ID is not available" seen in production: publish 400s
    # once right after create, then succeeds on the retry.
    monkeypatch.setattr(threads_module, "PUBLISH_RETRY_DELAYS", (0.0, 0.0))

    class NotReadyOnce(FakeSession):
        def __init__(self):
            super().__init__()
            self.publish_attempts = 0

        def post(self, url, data=None, timeout=None):
            if url.endswith("/threads_publish"):
                self.publish_attempts += 1
                if self.publish_attempts == 1:
                    return _Resp({"error": "Media ID is not available"}, status_code=400)
            return super().post(url, data=data, timeout=timeout)

    svc = ThreadsService(session=NotReadyOnce(), access_token="tok", user_id="17800000")
    assert svc.post_post("hello") == "901"
    assert svc.session.publish_attempts == 2


def test_container_error_status_raises_with_meta_detail(monkeypatch):
    monkeypatch.setattr(threads_module, "CONTAINER_READY_DELAYS", (0.0,))

    class ErrorContainer(FakeSession):
        container_status = "ERROR"

    svc = ThreadsService(session=ErrorContainer(), access_token="tok", user_id="17800000")
    with pytest.raises(RuntimeError, match="ERROR.*boom detail"):
        svc.post_post("hello")


def test_post_thread_partial_failure_carries_live_ids(monkeypatch):
    monkeypatch.setattr(threads_module, "PUBLISH_RETRY_DELAYS", ())

    class DiesOnSecond(FakeSession):
        def post(self, url, data=None, timeout=None):
            if url.endswith("/threads") and data.get("reply_to_id"):
                raise RuntimeError("boom")
            return super().post(url, data=data, timeout=timeout)

    svc = ThreadsService(session=DiesOnSecond(), access_token="tok", user_id="17800000")
    with pytest.raises(PartialThreadError) as err:
        svc.post_thread(["one", "two"])
    assert err.value.ids == ["901"]
