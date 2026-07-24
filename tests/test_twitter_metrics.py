"""TwitterService.get_metrics: user-context auth, chunking, public-only fallback."""
from services.twitter import TwitterService


class _Tweet:
    def __init__(self, tid, pm, npm=None, org=None):
        self.id = tid
        self.public_metrics = pm
        self.non_public_metrics = npm
        self.organic_metrics = org


class _Resp:
    def __init__(self, data):
        self.data = data


class FakeClient:
    def __init__(self, fail_npm=False, fail_organic=False):
        self.calls = []
        self.fail_npm = fail_npm
        self.fail_organic = fail_organic

    def get_tweets(self, ids, tweet_fields=None, user_auth=False):
        self.calls.append({"ids": list(ids), "fields": list(tweet_fields), "user_auth": user_auth})
        if self.fail_npm and "non_public_metrics" in tweet_fields:
            raise RuntimeError("403 non_public_metrics requires user context")
        if self.fail_organic and "organic_metrics" in tweet_fields:
            raise RuntimeError("400 organic_metrics not available on this tier")
        pm = {"like_count": 1, "reply_count": 2, "retweet_count": 3, "quote_count": 0, "bookmark_count": 6}
        npm = {"impression_count": 500, "url_link_clicks": 7} if "non_public_metrics" in tweet_fields else None
        org = {"user_profile_clicks": 9} if "organic_metrics" in tweet_fields else None
        return _Resp([_Tweet(i, pm, npm, org) for i in ids])


def test_metrics_use_user_context_auth_and_growth_signals():
    svc = TwitterService(client=FakeClient())
    out = svc.get_metrics(["1", "2"])
    assert svc.client.calls[0]["user_auth"] is True
    assert out["1"]["impressions"] == 500
    assert out["1"]["link_clicks"] == 7
    assert out["1"]["bookmarks"] == 6          # public_metrics
    assert out["1"]["profile_clicks"] == 9     # organic_metrics (growth proxy)
    assert out["2"]["likes"] == 1


def test_metrics_fall_back_through_field_sets():
    # non_public AND organic rejected → third try (public-only) succeeds.
    svc = TwitterService(client=FakeClient(fail_npm=True))
    out = svc.get_metrics(["1"])
    assert len(svc.client.calls) == 3
    assert svc.client.calls[-1]["fields"] == ["public_metrics"]
    assert out["1"]["likes"] == 1
    assert out["1"]["bookmarks"] == 6
    # impressions/profile_clicks omitted (not zeroed) so Notion values survive
    assert "impressions" not in out["1"] and "profile_clicks" not in out["1"]


def test_metrics_fall_back_organic_only():
    # organic rejected but non_public accepted → second try wins, no profile clicks.
    svc = TwitterService(client=FakeClient(fail_organic=True))
    out = svc.get_metrics(["1"])
    assert len(svc.client.calls) == 2
    assert out["1"]["impressions"] == 500
    assert "profile_clicks" not in out["1"]


def test_metrics_chunk_at_100_ids():
    svc = TwitterService(client=FakeClient())
    ids = [str(i) for i in range(150)]
    out = svc.get_metrics(ids)
    assert [len(c["ids"]) for c in svc.client.calls] == [100, 50]
    assert len(out) == 150
