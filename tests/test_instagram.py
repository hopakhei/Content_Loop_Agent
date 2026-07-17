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


# ── carousel publish ──────────────────────────────────────────────────────────

def test_publish_carousel_three_step():
    svc = _svc()
    mid = svc.publish_carousel(["https://h/1.png", "https://h/2.png", "https://h/3.png"], "一輯拆解")
    assert mid == "901"
    posts = svc.session.posts
    items = [p for p in posts if p[1].get("is_carousel_item") == "true"]
    assert len(items) == 3
    assert [p[1]["image_url"] for p in items] == ["https://h/1.png", "https://h/2.png", "https://h/3.png"]
    container = next(p for p in posts if p[1].get("media_type") == "CAROUSEL")
    assert container[1]["children"] == "C1,C2,C3"
    assert container[1]["caption"] == "一輯拆解"
    publish = next(p for p in posts if p[0].endswith("/media_publish"))
    assert publish[1]["creation_id"] == "C4"


def test_publish_carousel_rejects_bad_slide_count():
    svc = _svc()
    with pytest.raises(ValueError):
        svc.publish_carousel(["https://h/1.png"], "x")
    with pytest.raises(ValueError):
        svc.publish_carousel([f"https://h/{i}.png" for i in range(11)], "x")


def test_publish_carousel_dry_run_never_touches_network():
    svc = InstagramService(dry_run=True, access_token="", user_id="")
    assert svc.publish_carousel(["u1", "u2"], "x").startswith("DRYRUN-IG-")


# ── insights (Loop 2) ─────────────────────────────────────────────────────────

class InsightSession:
    """GET /{media}/insights returns a data[] series; /{uid} returns followers."""
    followers = 1234

    def __init__(self, reject_metrics=()):
        self.reject_metrics = set(reject_metrics)   # metric-set strings that 400
        self.insight_calls = []

    def get(self, url, params=None, timeout=None):
        params = params or {}
        if url.endswith("/insights"):
            metric = params.get("metric", "")
            self.insight_calls.append(metric)
            if metric in self.reject_metrics:
                return _Resp({"error": "unsupported metric"}, status_code=400)
            names = metric.split(",")
            data = [{"name": n, "values": [{"value": _V.get(n, 0)}]} for n in names]
            return _Resp({"data": data})
        if params.get("fields") == "followers_count":
            return _Resp({"followers_count": self.followers, "id": "178000"})
        return _Resp({"user_id": "178000", "username": "ninetypm_ig"})


_V = {"views": 900, "reach": 800, "likes": 40, "comments": 6,
      "saved": 12, "shares": 3, "profile_visits": 25}


def test_get_insights_normalizes_to_shared_schema():
    svc = _svc(InsightSession())
    out = svc.get_insights(["M1"])
    assert out["M1"] == {
        "impressions": 900,      # views
        "likes": 40,
        "replies": 6,            # comments
        "reposts": 3,            # shares
        "bookmarks": 12,         # saved (growth signal)
        "profile_clicks": 25,    # profile_visits (growth signal)
    }


def test_get_insights_falls_back_when_metric_set_rejected():
    # The richest set (with views/profile_visits) 400s; the loop degrades to the
    # next set, which resolves — impressions then come from reach.
    session = InsightSession(
        reject_metrics={"views,reach,likes,comments,saved,shares,profile_visits"})
    svc = _svc(session)
    out = svc.get_insights(["M1"])
    assert out["M1"]["impressions"] == 800     # reach (views set was rejected)
    assert out["M1"]["bookmarks"] == 12
    # first media probed 2 sets; the working set is then pinned for the rest
    assert session.insight_calls[0].startswith("views,")
    assert session.insight_calls[1].startswith("reach,")


def test_get_insights_pins_working_set_after_first_success():
    session = InsightSession(reject_metrics={
        "views,reach,likes,comments,saved,shares,profile_visits"})
    svc = _svc(session)
    svc.get_insights(["M1", "M2"])
    # M1 probes 2 sets (reject then ok); M2 uses only the pinned set → 3 total.
    assert len(session.insight_calls) == 3
    assert session.insight_calls[2].startswith("reach,")


def test_get_follower_count():
    assert _svc(InsightSession()).get_follower_count() == 1234


def test_insights_and_followers_are_noop_in_dry_run():
    svc = InstagramService(dry_run=True, access_token="", user_id="")
    assert svc.get_insights(["M1"]) == {}
    assert svc.get_follower_count() is None
