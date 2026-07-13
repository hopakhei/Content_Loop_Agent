"""InstagramService: two-step image publish, ready-poll, verify — fake session."""
import pytest

from services import instagram as ig_module
from services.instagram import InstagramService


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} error")

    def json(self):
        return self._payload


class FakeSession:
    container_status = "FINISHED"

    def __init__(self):
        self.posts = []
        self.gets = []
        self._creation = 0
        self._published = 0

    def get(self, url, params=None, timeout=None):
        self.gets.append((url, dict(params or {})))
        if (params or {}).get("fields", "").startswith("status_code"):
            return _Resp({"status_code": self.container_status})
        return _Resp({"user_id": "178000", "username": "ninetypm_ig"})

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, dict(data)))
        if url.endswith("/media_publish"):
            self._published += 1
            return _Resp({"id": f"90{self._published}"})
        self._creation += 1
        return _Resp({"id": f"C{self._creation}"})


def _svc(session=None):
    return InstagramService(session=session or FakeSession(), access_token="tok", user_id="178000")


def test_verify_returns_handle():
    assert _svc().verify() == "ninetypm_ig"


def test_publish_image_two_step():
    svc = _svc()
    mid = svc.publish_image("https://host/card.png", "一句金句\n\nlink in bio")
    assert mid == "901"
    create, publish = svc.session.posts
    assert create[0].endswith("/178000/media")
    assert create[1]["image_url"] == "https://host/card.png"
    assert create[1]["caption"].startswith("一句金句")
    assert publish[0].endswith("/178000/media_publish")
    assert publish[1]["creation_id"] == "C1"
    # a status poll happened before publish
    assert any(g[1].get("fields", "").startswith("status_code") for g in svc.session.gets)


def test_container_error_raises(monkeypatch):
    monkeypatch.setattr(ig_module, "CONTAINER_READY_DELAYS", (0.0,))

    class ErrSession(FakeSession):
        container_status = "ERROR"

    with pytest.raises(RuntimeError, match="ERROR"):
        _svc(ErrSession()).publish_image("https://host/c.png", "x")


def test_publish_retries_client_error(monkeypatch):
    monkeypatch.setattr(ig_module, "PUBLISH_RETRY_DELAYS", (0.0, 0.0))
    monkeypatch.setattr(ig_module, "CONTAINER_READY_DELAYS", (0.0,))

    class Flaky(FakeSession):
        def __init__(self):
            super().__init__()
            self.pub_tries = 0

        def post(self, url, data=None, timeout=None):
            if url.endswith("/media_publish"):
                self.pub_tries += 1
                if self.pub_tries == 1:
                    return _Resp({"error": "Media not ready"}, status_code=400)
            return super().post(url, data=data, timeout=timeout)

    svc = _svc(Flaky())
    assert svc.publish_image("https://host/c.png", "x") == "901"
    assert svc.session.pub_tries == 2


def test_dry_run_never_touches_network():
    svc = InstagramService(dry_run=True, access_token="", user_id="")
    mid = svc.publish_image("https://host/c.png", "x")
    assert mid.startswith("DRYRUN-IG-")
    assert svc.session is None
