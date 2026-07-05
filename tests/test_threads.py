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
        self._creation = 0
        self._published = 0

    def get(self, url, params=None, timeout=None):
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
