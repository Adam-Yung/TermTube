import time

from src import fuzzy


def _e(title, uploader=""):
    return {"id": title, "title": title, "uploader": uploader}


def _titles(entries):
    return [e["title"] for e in entries]


def test_empty_query_returns_everything_in_order():
    entries = [_e("b"), _e("a")]
    assert fuzzy.rank(entries, "") == entries
    assert fuzzy.rank(entries, "   ") == entries


def test_case_insensitive_and_all_tokens_must_match():
    entries = [_e("Python Tutorial"), _e("Python Tips"), _e("Rust Tutorial")]
    assert _titles(fuzzy.rank(entries, "PYTHON tutorial")) == ["Python Tutorial"]
    assert fuzzy.rank(entries, "python zig") == []


def test_tokens_may_match_title_and_uploader():
    entries = [_e("Intro", "Fireship"), _e("Intro", "Other")]
    assert [e["uploader"] for e in fuzzy.rank(entries, "intro fire")] == ["Fireship"]


def test_prefix_beats_word_start_beats_inside():
    entries = [_e("concatenate"), _e("the cat sat"), _e("cat video")]
    assert _titles(fuzzy.rank(entries, "cat")) == ["cat video", "the cat sat", "concatenate"]


def test_ties_keep_original_order():
    entries = [_e("x one"), _e("x two"), _e("x three")]
    assert _titles(fuzzy.rank(entries, "x")) == ["x one", "x two", "x three"]


def test_title_beats_uploader():
    entries = [_e("Other", "music"), _e("music", "Other")]
    assert _titles(fuzzy.rank(entries, "music")) == ["music", "Other"]


def test_unicode_accents_and_case():
    entries = [_e("Café Müller"), _e("日本語の動画"), _e("Straße")]
    assert _titles(fuzzy.rank(entries, "cafe muller")) == ["Café Müller"]
    assert _titles(fuzzy.rank(entries, "日本")) == ["日本語の動画"]
    assert _titles(fuzzy.rank(entries, "STRASSE")) == ["Straße"]
    assert _titles(fuzzy.rank(entries, "straße")) == ["Straße"]


def test_missing_fields_do_not_crash():
    assert fuzzy.rank([{"id": "1"}, {"title": None, "uploader": None}], "x") == []


def test_ten_thousand_rows_rank_quickly():
    entries = [_e(f"Video number {i} about topic {i % 97}", f"Channel {i % 50}") for i in range(10_000)]
    start = time.perf_counter()
    result = fuzzy.rank(entries, "topic 42 chan")
    elapsed = time.perf_counter() - start
    assert result and elapsed < 0.05
