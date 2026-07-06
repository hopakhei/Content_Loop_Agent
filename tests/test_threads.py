"""ThreadsService: two-step publish, reply chaining, verify — with a fake session."""
from services.threads import ThreadsService


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    """Returns creation ids on /threads and post ids on /threads_publish."""

    def __init__(self):
        self.posts = []   # (url, data) for POSTs
        self.gets = []    # (url, params) for GETs
        self._creation = 0
        self._published = 0

    def get(self, url, params=None, timeout=None):
        self.gets.append((url, dict(params or {})))
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
