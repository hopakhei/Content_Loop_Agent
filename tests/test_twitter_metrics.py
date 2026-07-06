"""TwitterService.get_metrics: user-context auth, chunking, public-only fallback."""
from services.twitter import TwitterService


class _Tweet:
    def __init__(self, tid, pm, npm=None):
        self.id = tid
        self.public_metrics = pm
        self.non_public_metrics = npm


class _Resp:
    def __init__(self, data):
        self.data = data


class FakeClient:
    def __init__(self, fail_npm=False):
        self.calls = []
        self.fail_npm = fail_npm

    def get_tweets(self, ids, tweet_fields=None, user_auth=False):
        self.calls.append({"ids": list(ids), "fields": list(tweet_fields), "user_auth": user_auth})
        if self.fail_npm and "non_public_metrics" in tweet_fields:
            raise RuntimeError("403 non_public_metrics requires user context")
        npm = {"impression_count": 500, "url_link_clicks": 7} if "non_public_metrics" in tweet_fields else None
        pm = {"like_count": 1, "reply_count": 2, "retweet_count": 3, "quote_count": 0}
        return _Resp([_Tweet(i, pm, npm) for i in ids])


def test_metrics_use_user_context_auth():
    svc = TwitterService(client=FakeClient())
    out = svc.get_metrics(["1", "2"])
    assert svc.client.calls[0]["user_auth"] is True
    assert out["1"]["impressions"] == 500
    assert out["1"]["link_clicks"] == 7
    assert out["2"]["likes"] == 1


def test_metrics_fall_back_to_public_only():
    svc = TwitterService(client=FakeClient(fail_npm=True))
    out = svc.get_metrics(["1"])
    assert len(svc.client.calls) == 2
    assert "non_public_metrics" not in svc.client.calls[1]["fields"]
    assert out["1"]["likes"] == 1
    # impressions omitted (not zeroed) so existing Notion values survive
    assert "impressions" not in out["1"]


def test_metrics_chunk_at_100_ids():
    svc = TwitterService(client=FakeClient())
    ids = [str(i) for i in range(150)]
    out = svc.get_metrics(ids)
    assert [len(c["ids"]) for c in svc.client.calls] == [100, 50]
    assert len(out) == 150
