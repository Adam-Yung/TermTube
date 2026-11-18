"""Library filter tokens: `key:value` on top of free text; invalid tokens fall back to free text."""

import pytest

from src import library_query


def row(vid, title, **extra):
    return {"id": vid, "title": title, **extra}


ENTRIES = [
    row("a", "Jazz Night", uploader="Café Blue", duration=300, upload_date="20240105", _local_type="audio",
        _local_path="/x/a.mp3", description="smooth piano", tags=["live", "piano"]),
    row("b", "Rust Talk", uploader="Dev Conf", duration=3000, upload_date="20230210", _local_type="video",
        _local_path="/x/b.mp4"),
    row("c", "Cats", uploader="Pets", duration=90, upload_date="20240301"),
    row("d", "Both Forms", uploader="Dev Conf", duration=1500, _local_type="video", _has_audio=True,
        _local_path="/x/d.mp4"),
]


def ids(text, membership=None):
    return [e["id"] for e in library_query.rank(ENTRIES, text, membership)]


def test_plain_text_matches_title_uploader_description_and_tags():
    assert ids("jazz") == ["a"]
    assert ids("dev conf") == ["b", "d"]
    assert ids("piano") == ["a"]
    assert ids("") == ["a", "b", "c", "d"]


def test_accents_and_case_are_ignored():
    assert ids("CAFE") == ["a"]
    assert ids("by:café") == ["a"]


def test_type_token_counts_the_audio_file_of_a_video_row():
    assert ids("type:audio") == ["a", "d"]
    assert ids("type:video") == ["b", "d"]
    assert ids("TYPE:Audio piano") == ["a"]


def test_dur_token_with_units_and_clock_formats():
    assert ids("dur:<10m") == ["a", "c"]
    assert ids("dur:>20m") == ["b", "d"]
    assert ids("dur:>1h") == []
    assert ids("dur:<1:30") == []
    assert ids("dur:<1:31") == ["c"]
    assert library_query.parse_duration("1h30m") == 5400
    assert library_query.parse_duration("90") == 90
    assert library_query.parse_duration("soon") is None


def test_year_by_and_dl_tokens():
    assert ids("year:2024") == ["a", "c"]
    assert ids("by:pets") == ["c"]
    assert ids("dl:no") == ["c"]
    assert ids("dl:yes year:2024") == ["a"]


def test_quoted_value_keeps_its_space_and_unclosed_quote_runs_to_the_end():
    assert ids('by:"dev conf"') == ["b", "d"]
    assert ids('by:"dev conf') == ["b", "d"]
    assert ids('"rust talk"') == ["b"]


@pytest.mark.parametrize("text", ["type:movie", "dur:soon", "dur:10m", "year:24", "dl:maybe", "by:", "nokey:x"])
def test_invalid_tokens_degrade_to_free_text(text):
    assert ids(text) == []
    assert library_query.parse(text).checks == []


def test_pl_token_uses_one_membership_lookup_and_only_when_asked():
    calls = []

    def membership():
        calls.append(1)
        return {"a": ["Late night"], "b": ["Work", "Late shift"]}

    assert ids("pl:late", membership) == ["a", "b"]
    assert ids("pl:work", membership) == ["b"]
    assert len(calls) == 2
    ids("jazz", membership)
    assert len(calls) == 2


def test_free_text_ranks_best_match_first_when_tokens_filter_the_rest():
    entries = [row("x", "a cat video", uploader="U"), row("y", "Cat", uploader="U"), row("z", "dog", uploader="U")]
    assert [e["id"] for e in library_query.rank(entries, "cat")] == ["y", "x"]
