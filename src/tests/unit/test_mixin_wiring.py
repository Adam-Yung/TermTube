"""Static wiring of the screens built from mixins: what the MRO resolves, not what each mixin does alone.

A no-op hook in one mixin once shadowed the loader's real one, so Home never loaded more pages while every
per-feature test passed. These checks read the classes and fail on that whole family of defect.
"""

import ast
import importlib
import inspect
import pkgutil
import re
import textwrap

import pytest
from textual.message import Message
from textual.screen import Screen

import src.tui
from src.tui.screens.channel_screen import ChannelScreen
from src.tui.screens.main_screen import MainScreen
from src.tui.screens.queue_screen import QueueScreen

HOSTS = [MainScreen, ChannelScreen, QueueScreen]

# name -> class that must win on each host. Every other duplicate across the MRO is a failure.
# Screens refine a mixin's default (calling super() where it extends it); PlaylistToolsMixin and LibraryRailMixin
# refine ListToolsMixin because the Library tab owns playlists and the rail; on_key handlers all run (Textual
# dispatches each class's own handler until one calls prevent_default), ListToolsMixin first so an open
# removal question swallows the key.
OVERRIDES = {
    "MainScreen": {
        "_tool_actions": "MainScreen",
        "panel_hints": "MainScreen",
        "_selected_entry": "MainScreen",
        "_activate_entry": "MainScreen",
        "_cancel_pending_focus_and_thumb": "MainScreen",
        "_worker_start": "MainScreen",
        "_worker_end": "MainScreen",
        "_removal_key": "PlaylistToolsMixin",
        "_delete_targets": "PlaylistToolsMixin",
        "_playlist_source": "PlaylistToolsMixin",
        "on_key": "ListToolsMixin",
        "action_page_prev": "LibraryRailMixin",
    },
    "ChannelScreen": {
        "_tool_actions": "ChannelScreen",
        "_hidden_menu_actions": "ChannelScreen",
        "action_channel": "ChannelScreen",
        "action_page_next": "ChannelScreen",
        "action_goto_end": "ChannelScreen",
        "_activate_entry": "ChannelPlaylistMixin",
    },
    "QueueScreen": {
        "action_activate": "QueueScreen",
        "panel_hints": "QueueScreen",
        "on_audio_queue_changed": "QueueScreen",
        "on_audio_track_changed": "QueueScreen",
        "on_player_state_updated": "QueueScreen",
    },
}

# Hooks whose winning definition may do nothing, with the reason.
# ChannelScreen has no spinner and prefetches from its own page actions.
EMPTY_HOOKS = {
    ("QueueScreen", "_worker_start"): "no header spinner on the queue page",
    ("QueueScreen", "_worker_end"): "no header spinner on the queue page",
    ("QueueScreen", "_on_page_shown"): "the queue is held whole",
    ("QueueScreen", "_on_past_last_page"): "the queue is held whole",
    ("ChannelScreen", "_worker_start"): "no header spinner on a channel page",
    ("ChannelScreen", "_worker_end"): "no header spinner on a channel page",
    ("ChannelScreen", "_on_page_shown"): "the page actions prefetch themselves",
}

# The queue page redraws its rows on the messages AudioBarMixin mirrors into the bar; Textual runs both handlers.
DUPLICATE_HANDLERS_OK = {"on_key", "on_audio_queue_changed", "on_audio_track_changed", "on_player_state_updated"}


def _own(cls):
    return [c for c in cls.__mro__ if c.__module__.startswith("src.tui")]


def _tree(cls):
    return ast.parse(textwrap.dedent(inspect.getsource(cls)))


def _is_empty(fn) -> bool:
    body = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0].body
    body = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    return all(
        isinstance(s, ast.Pass) or (isinstance(s, ast.Return) and s.value is None) for s in body
    )


def _definers(host):
    names: dict[str, list[type]] = {}
    for cls in _own(host):
        for name in vars(cls):
            if not name.startswith("__"):
                names.setdefault(name, []).append(cls)
    return names


@pytest.mark.parametrize("host", HOSTS, ids=lambda h: h.__name__)
def test_every_override_is_listed_and_the_listed_class_wins(host):
    duplicates = {n: [c.__name__ for c in cs] for n, cs in _definers(host).items() if len(cs) > 1}
    allowed = OVERRIDES[host.__name__]
    assert set(duplicates) == set(allowed), (
        f"unlisted: {sorted(set(duplicates) - set(allowed))}, stale: {sorted(set(allowed) - set(duplicates))}"
    )
    for name, winner in allowed.items():
        assert duplicates[name][0] == winner, f"{host.__name__}.{name}: {duplicates[name]}"


@pytest.mark.parametrize("host", HOSTS, ids=lambda h: h.__name__)
def test_no_mixin_shadows_a_textual_name(host):
    textual = [c for c in host.__mro__ if not c.__module__.startswith("src.tui") and c is not object]
    for cls in _own(host)[1:]:
        for name in vars(cls):
            hit = next((b.__name__ for b in textual if name in vars(b)), None)
            assert name.startswith("__") or hit is None, f"{cls.__name__}.{name} shadows {hit}.{name}"


@pytest.mark.parametrize("host", HOSTS, ids=lambda h: h.__name__)
def test_hooks_the_host_calls_are_not_silent_stubs(host):
    for name, classes in _definers(host).items():
        fn = vars(classes[0]).get(name)
        if not inspect.isfunction(fn) or not _is_empty(fn):
            continue
        assert (host.__name__, name) in EMPTY_HOOKS, f"{classes[0].__name__}.{name} is a no-op stub"


@pytest.mark.parametrize("host", HOSTS, ids=lambda h: h.__name__)
def test_empty_hook_allow_list_has_no_stale_entries(host):
    definers = _definers(host)
    for hosted, name in EMPTY_HOOKS:
        if hosted != host.__name__:
            continue
        fn = vars(definers[name][0]).get(name)
        assert inspect.isfunction(fn) and _is_empty(fn), f"{hosted}.{name} is no longer empty"


@pytest.mark.parametrize("host", HOSTS, ids=lambda h: h.__name__)
def test_every_self_attribute_a_mixin_uses_exists_on_its_host(host):
    """A mixin's contract (``Needs _worker_start ...``) is met when each ``self.x`` it reads resolves on the host."""
    assigned = set()
    for cls in _own(host):
        for node in ast.walk(_tree(cls)):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
                if isinstance(node.ctx, ast.Store):
                    assigned.add(node.attr)
    missing = {}
    for cls in _own(host):
        for node in ast.walk(_tree(cls)):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"
                and isinstance(node.ctx, ast.Load)
                and node.attr not in assigned
                and not hasattr(host, node.attr)
            ):
                missing.setdefault(cls.__name__, set()).add(node.attr)
    assert not missing, f"{host.__name__} lacks what its classes use: {missing}"


def _screen_classes():
    seen = []
    for mod in pkgutil.walk_packages(src.tui.__path__, "src.tui."):
        module = importlib.import_module(mod.name)
        for obj in vars(module).values():
            if inspect.isclass(obj) and obj.__module__ == module.__name__ and obj not in seen:
                seen.append(obj)
    return seen


def _action_target(action: str) -> tuple[str, str]:
    """(namespace, method) of a binding action; ``screen.x`` runs on the screen the widget sits in."""
    name = re.split(r"[(\s]", action, maxsplit=1)[0]
    namespace, _, name = name.rpartition(".")
    return namespace, "action_" + name


@pytest.mark.parametrize("cls", [c for c in _screen_classes() if "BINDINGS" in vars(c)], ids=lambda c: c.__name__)
def test_every_bound_key_dispatches_to_a_real_action(cls):
    from src.tui.app import TermTubeApp

    for binding in cls.BINDINGS:
        namespace, method = _action_target(binding.action)
        owner = {"": cls, "screen": MainScreen, "app": TermTubeApp}[namespace]
        assert hasattr(owner, method), f"{cls.__name__}: {binding.key} -> {binding.action}"


@pytest.mark.parametrize("host", HOSTS, ids=lambda h: h.__name__)
def test_the_main_screens_do_not_gate_actions(host):
    """No ``check_action``: every bound key reaches its action. If one is added, test each gated key."""
    assert host.check_action is Screen.check_action


@pytest.mark.parametrize("host", HOSTS, ids=lambda h: h.__name__)
def test_message_handlers_defined_twice_are_listed(host):
    handlers = {n: cs for n, cs in _definers(host).items() if n.startswith("on_") and len(cs) > 1}
    assert set(handlers) <= DUPLICATE_HANDLERS_OK, sorted(set(handlers) - DUPLICATE_HANDLERS_OK)


def _messages():
    out = []
    for cls in _screen_classes():
        for inner in [cls, *[v for v in vars(cls).values() if inspect.isclass(v)]]:
            if issubclass(inner, Message) and inner.__module__.startswith("src.tui") and inner not in out:
                out.append(inner)
    return out


def test_the_scan_finds_the_messages_the_app_posts():
    names = {m.__name__ for m in _messages()}
    assert {"Selected", "Activated", "PageChangeRequested", "PlayerStateUpdated", "Chosen"} <= names


@pytest.mark.parametrize("message", _messages(), ids=lambda m: m.__qualname__)
def test_every_message_class_has_a_handler_somewhere(message):
    handler = message.handler_name
    owners = [c for c in _screen_classes() if handler in vars(c)]
    assert owners, f"{message.__qualname__} is never handled ({handler})"


AUDIO_MESSAGES = [m for m in _messages() if m.__module__ == "src.tui.messages"]


@pytest.mark.parametrize("message", AUDIO_MESSAGES, ids=lambda m: m.__name__)
def test_every_screen_with_the_audio_bar_handles_the_audio_messages(message):
    for host in HOSTS:
        assert hasattr(host, message.handler_name), f"{host.__name__} drops {message.__name__}"


def test_a_screen_with_a_detail_panel_has_the_audio_bar_mixin():
    from src.tui.screens.mixins.audio_bar import AudioBarMixin
    from src.tui.screens.mixins.detail_focus import DetailFocusMixin

    for cls in _screen_classes():
        if issubclass(cls, Screen) and issubclass(cls, DetailFocusMixin):
            assert issubclass(cls, AudioBarMixin), cls.__name__
