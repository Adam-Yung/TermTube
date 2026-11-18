"""Rail collections of the Library and the download state attached to playlist rows."""

from src import library


def lib(vid, kind, **extra):
    return {"id": vid, "_local_type": kind, "_local_path": f"/m/{vid}", "_size": 5, **extra}


LIB = [lib("v", "video"), lib("a", "audio"), lib("b", "video", _has_audio=True, _audio_path="/m/b.mp3"),
       lib("m", "video", _missing_file=True)]


def test_kinds_of_and_counts():
    assert library.kinds(LIB[2]) == {"video", "audio"} and library.kinds({"id": "x"}) == set()
    assert [e["id"] for e in library.of_kind(LIB, "audio")] == ["a", "b"]
    assert [e["id"] for e in library.of_kind(LIB, "video")] == ["v", "b", "m"]
    assert library.counts(LIB) == {"": 4, "video": 3, "audio": 2}


def test_attach_local_marks_each_row_and_copies_the_file_fields():
    rows = [{"id": "v", "title": "V"}, {"id": "a"}, {"id": "b"}, {"id": "m"}, {"id": "gone"}]
    out = {r["id"]: r for r in library.attach_local(rows, LIB)}
    assert [out[k]["_dl"] for k in ("v", "a", "b", "m", "gone")] == ["video", "audio", "both", "", ""]
    assert out["v"]["_local_path"] == "/m/v" and out["b"]["_audio_path"] == "/m/b.mp3"
    assert "_local_path" not in out["m"] and "_local_path" not in out["gone"]
    assert "_dl" not in rows[0]
