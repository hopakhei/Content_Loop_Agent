"""core.tagging: machine-tag construction for Performance rows."""
from core.tagging import COMPOSITION_VERSION, build_tags, domain_of, len_bucket, series_of


def test_domain_of():
    assert domain_of("https://90spminvesting.substack.com/p/x?r=1") == "substack.com"
    assert domain_of("https://github.com/Draw-Tree/tree-quant-ledger") == "github.com"
    assert domain_of("http://localhost") == "localhost"
    assert domain_of(None) is None
    assert domain_of("not a url") is None


def test_series_of():
    assert series_of("#201-04 數據衝擊") == "2xx"
    assert series_of("#104-05 假設") == "1xx"
    assert series_of("no marker") is None
    assert series_of(None) is None


def test_len_bucket():
    assert len_bucket("a" * 140) == "short"
    assert len_bucket("a" * 141) == "mid"
    assert len_bucket("a" * 280) == "mid"
    assert len_bucket("a" * 281) == "long"
    assert len_bucket("") == "short"


def test_build_tags_full():
    tags = build_tags(
        platform="X", hook="A", posts=["hello"],
        cta_url="https://github.com/Draw-Tree/tree-quant-ledger",
        cta_present=True, title="#201-04 x", extra={"x_link_arm": "link"},
    )
    assert tags == {
        "platform": "X", "hook": "A", "has_link": True, "link_domain": "github.com",
        "chain_len": 1, "series": "2xx", "len_bucket": "short",
        "comp": COMPOSITION_VERSION, "x_link_arm": "link",
    }


def test_build_tags_drops_none_and_link_free():
    # No hook, no link → hook and link_domain keys are dropped; has_link False.
    tags = build_tags(
        platform="X", hook=None, posts=["body"], cta_url="https://x.substack.com/p/1",
        cta_present=False, title="untitled",
    )
    assert "hook" not in tags and "link_domain" not in tags and "series" not in tags
    assert tags["has_link"] is False
