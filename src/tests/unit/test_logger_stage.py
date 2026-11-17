"""Tests for logger.stage: startup milestones are logged once and only with --debug."""

import logging

from src import logger


def _records(caplog):
    return [r.getMessage() for r in caplog.records if "startup stage" in r.getMessage()]


def test_stage_logs_once_with_deltas(caplog):
    logger.setup(debug=True)
    logger._log.propagate = True
    try:
        with caplog.at_level(logging.DEBUG, logger="termtube"):
            logger.stage("first paint")
            logger.stage("first paint")
            logger.stage("first rows")
        msgs = _records(caplog)
        assert len(msgs) == 2
        assert msgs[0].startswith("startup stage first paint: +")
        assert "ms since start" in msgs[1]
    finally:
        logger._log.propagate = False
        logger.setup(debug=False)


def test_stage_is_silent_without_debug(caplog):
    logger.setup(debug=False)
    logger._log.propagate = True
    try:
        with caplog.at_level(logging.DEBUG, logger="termtube"):
            logger.stage("config loaded")
        assert _records(caplog) == []
    finally:
        logger._log.propagate = False
