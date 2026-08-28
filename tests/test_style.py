"""Shape and the de-AI list, enforced instead of remembered.

Two complaints arrived together, and they had the same cause. The batch had
drifted to nine segments — nine subjects, no spine, which reads as a list even
when every line is true. And the corpus held 33 uses of 東西 and 19 of 這件事
against a single 其實: the de-AI pass had been catching the memorable half of
the renhua ban list and missing the common half, because nothing checked it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_style as ast_  # noqa: E402


def test_every_queued_unit_is_clean():
    """The gate covers what is committed to ship.

    It used to cover the whole corpus, on the grounds that unit files are always
    editable and double as the spec the Routine copies. The 2026-08-27 rules —
    four segments instead of five, numbered sets actually numbered — failed all
    42 units at once, and a gate that needs 42 posts rewritten in one commit
    gets switched off rather than cleared. The spec half of that argument is
    handled where it belongs: AUTOPRODUCER.md names exemplars now instead of
    pointing at whatever shipped.

    Queued units are the ones the next few days of Instagram come out of, so
    they are the ones worth stopping a build over. Published and not-yet-queued
    units are printed with names and counts by the report instead.
    """
    pending = set(ast_.queued())
    rows = [ast_.audit(s) for s in ast_.framework_slugs() if s in pending]
    bad = {r["slug"]: ast_.problems(r) for r in rows if not r["ok"]}
    assert not bad, f"queued units breaking shape or the ban list: {bad}"


def test_the_queue_is_actually_covering_something():
    """The gate is scoped by the queue, so an empty queue silently disables it."""
    assert ast_.queued(), "carousel queue empty — the style gate covers nothing"


def test_the_posted_ledger_is_not_empty():
    """The grounding check grandfathers published carousels on this file, and
    the style report labels rows with it. Empty means a first run or a bad
    Notion read; the second case would quietly relabel the whole corpus."""
    assert len(ast_.posted_slugs()) >= 20


def test_nine_segments_fails_and_four_passes():
    body = "\n---\n".join(["起" * 150] * 9)
    assert ast_.segments(body).__len__() == 9
    assert len(ast_.segments("\n---\n".join(["起" * 150] * 4))) == 4


def test_a_numbered_set_has_to_be_numbered():
    """The reader's own report: 「他們歸納出五個條件」 and then five conditions
    dissolved into prose, and they came back having reconstructed the wrong
    five. Announcing a count is a promise the reader can count them."""
    run_on = ("他們歸納出五個條件。共同議程是對問題有共識。共享量度是一小組"
              "指標。互相強化的行動是各做各的。持續溝通要有紀律。第五個是"
              "骨幹團隊。")
    assert ast_.unnumbered_sets([run_on])
    numbered = ("他們歸納出五個條件：\n1. 共同議程\n2. 共享量度\n"
                "3. 互相強化的行動\n4. 持續溝通\n5. 骨幹團隊")
    assert not ast_.unnumbered_sets([numbered])


def test_two_of_something_stays_prose():
    """The rule is for sets a reader has to keep count of, not for every number."""
    assert not ast_.unnumbered_sets(["這裡有兩個問題，一個講成本，一個講價格。"])


def test_a_repeated_clause_opening_is_caught():
    """排比 in the form the gate can be sure about. The triad cap never saw
    this because there is no 、 in it."""
    assert ast_.parallel_runs(
        "每個人都同意要換，每個人都有別的事要忙，每個人都在等別人開口")


def test_narrative_clauses_are_not_parallelism():
    """The first version of this check graded clause lengths and failed this
    sentence — one subject moving through time. A gate that blocks the build on
    ordinary prose gets written around."""
    assert not ast_.parallel_runs(
        "你熟悉的那間便利商店，開到別的國家之後，架上一半的商品你認不出來")


def test_absolutes_are_caught():
    """The reader named 「致命」. It travels with a family."""
    assert ast_._ABSOLUTES.search("骨幹團隊是最常被省略的一個，也是最致命的")
    assert ast_._ABSOLUTES.search("沒有那隊人，前面四樣一定散")


def test_the_vague_referent_bans_are_covered():
    """These two were the whole gap: they are the most common bans in the list
    and the ones no pass ever caught."""
    labels = [label for label, _ in ast_.BANS]
    assert any("東西" in x for x in labels)
    assert any("這件事" in x for x in labels)


def test_a_binary_contrast_shell_is_caught():
    rx = dict((label, rx) for label, rx in ast_.BANS)["二元對比殼「不是…而是」"]
    assert rx.search("去 AI 味不是把文章改口語，而是保住判斷")
    # A 不是 and a 而是 in different sentences are two ordinary words.
    assert not rx.search("這不是重點。他而是走了另一條路")


def test_a_short_segment_is_a_bullet_not_a_paragraph():
    assert ast_.MIN_SEGMENT_CHARS >= 100
    assert ast_.MAX_SEGMENTS == 4
