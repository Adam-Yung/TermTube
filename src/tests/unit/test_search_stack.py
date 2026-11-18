"""The search stack: push, dedupe, cap, pop, saved position."""

from src.search_stack import MAX_DEPTH, SearchStack


def depth(stack):
    """Frames in the stack, counted by popping a throwaway copy's way back."""
    n = 1 if stack.query else 0
    while stack.pop():
        n += 1
    return n


def test_push_and_pop_walk_back():
    stack = SearchStack()
    stack.push("a")
    stack.push("b")
    assert stack.query == "b"
    assert stack.pop() and stack.query == "a"
    assert not stack.pop() and stack.query == "a"


def test_same_query_as_the_top_is_not_pushed_again():
    stack = SearchStack()
    stack.push("a")
    stack.push("a")
    assert depth(stack) == 1


def test_depth_is_capped_and_drops_the_oldest():
    stack = SearchStack()
    for i in range(MAX_DEPTH + 5):
        stack.push(f"q{i}")
    assert depth(stack) == MAX_DEPTH
    assert stack.query == "q5"


def test_position_is_returned_once():
    stack = SearchStack()
    stack.push("a")
    stack.save_position(3, "vid")
    assert stack.take_position() == (3, "vid")
    assert stack.take_position() == (1, None)


def test_breadcrumb_only_with_something_to_go_back_to():
    stack = SearchStack()
    stack.push("a")
    assert stack.breadcrumb() == ""
    stack.push("b")
    assert "“a”" in stack.breadcrumb() and "2 searches" in stack.breadcrumb()
