from src.channel_pager import ChannelPager


def rows(n):
    return [{"id": f"v{i}"} for i in range(n)]


def test_wants_more_only_near_the_end_with_a_token_and_no_fetch_running():
    pager = ChannelPager()
    pager.start(30, "T1")
    assert not pager.wants_more(1, 3) and pager.wants_more(2, 3) and pager.wants_more(3, 3)
    pager.begin_fetch()
    assert not pager.wants_more(3, 3)
    pager.finish(rows(30), "")
    assert not pager.wants_more(3, 3)


def test_cap_trims_the_batch_and_drops_the_token():
    pager = ChannelPager(cap=50)
    pager.start(30, "T1")
    kept = pager.finish(rows(30), "T2")
    assert len(kept) == 20 and pager.loaded == 50 and pager.token == ""
    assert pager.note() == "first 50 shown"


def test_a_first_page_at_the_cap_has_no_more():
    pager = ChannelPager(cap=30)
    pager.start(30, "T1")
    assert pager.token == "" and not pager.wants_more(1, 1)


def test_note_names_the_size_of_the_batch_in_flight():
    pager = ChannelPager()
    pager.start(30, "T1")
    assert pager.note() == ""
    pager.begin_fetch()
    assert pager.note() == "loading 30 more…"
    pager.finish(rows(25), "T2")
    pager.begin_fetch()
    assert pager.note() == "loading 25 more…"


def test_a_failed_fetch_ends_paging():
    pager = ChannelPager()
    pager.start(30, "T1")
    pager.begin_fetch()
    assert pager.finish([], "") == [] and pager.token == "" and not pager.fetching


def test_reset_clears_everything():
    pager = ChannelPager()
    pager.start(30, "T1")
    pager.begin_fetch()
    pager.reset()
    assert (pager.token, pager.loaded, pager.fetching, pager.note()) == ("", 0, False, "")
