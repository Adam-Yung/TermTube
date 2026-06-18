"""Snapshot tests for visual regression detection.

These tests generate SVG screenshots of the app in various states.
First run generates baselines; subsequent runs compare against them.
Use `pytest --snapshot-update` to accept new baselines.
"""

import pytest

# Snapshot tests require pytest-textual-snapshot which may not be installed
# in all environments. Skip gracefully if unavailable.
pytest.importorskip("pytest_textual_snapshot")


def test_placeholder():
    """Placeholder until snapshot infrastructure is configured.

    To activate snapshot tests:
    1. pip install pytest-textual-snapshot
    2. Create an app launcher script that boots TermTubeApp with mocked data
    3. Use snap_compare with that script
    """
    pass
