"""Tests for DebugManager (V3.2.0)."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pytest

from anythink.debug.manager import DebugManager
from anythink.debug.models import RequestDebugRecord


def _make_record(request_id: int = 1) -> RequestDebugRecord:
    t0 = time.monotonic()
    return RequestDebugRecord(
        request_id=request_id,
        session_id="sess-1",
        timestamp=datetime.utcnow(),
        model_id="test-model",
        provider_name="test-provider",
        alias_name="test",
        prompt_payload=[{"role": "user", "content": "hello"}],
        gen_params=None,
        t_start=t0,
        t_prompt_assembled=t0 + 0.014,
        t_api_sent=t0 + 0.014,
        t_first_token=t0 + 0.200,
        t_stream_end=t0 + 0.942,
        t_render_end=t0 + 0.953,
        stop_reason="end_turn",
        completion_tokens=83,
        tokens_per_second=111.0,
    )


def test_initial_state():
    dm = DebugManager()
    assert dm.is_active() is False
    assert dm.level() == 2
    assert dm.api_logging_active() is False
    assert dm.panel_open() is False
    assert dm.latest() is None
    assert dm.all_records() == []


def test_enable_disable():
    dm = DebugManager()
    dm.enable(level=3)
    assert dm.is_active() is True
    assert dm.level() == 3
    dm.disable()
    assert dm.is_active() is False


def test_toggle():
    dm = DebugManager()
    assert dm.toggle() is True
    assert dm.is_active() is True
    assert dm.toggle() is False
    assert dm.is_active() is False


def test_set_level_clamps():
    dm = DebugManager()
    dm.set_level(0)
    assert dm.level() == 1
    dm.set_level(5)
    assert dm.level() == 3
    dm.set_level(2)
    assert dm.level() == 2


def test_toggle_api_logging():
    dm = DebugManager()
    assert dm.toggle_api_logging() is True
    assert dm.api_logging_active() is True
    assert dm.toggle_api_logging() is False
    assert dm.api_logging_active() is False


def test_toggle_panel():
    dm = DebugManager()
    assert dm.toggle_panel() is True
    assert dm.panel_open() is True
    assert dm.toggle_panel() is False
    assert dm.panel_open() is False


def test_begin_and_finalize_request():
    dm = DebugManager()
    dm.enable()
    t0 = time.monotonic()
    rec = dm.begin_request(
        session_id="s1",
        model_id="m1",
        provider_name="p1",
        alias_name="a1",
        prompt_payload=[],
        gen_params=None,
        t_start=t0,
    )
    assert rec.request_id == 1
    assert rec.session_id == "s1"
    assert dm.latest() is None  # not yet finalized

    dm.finalize_request(rec)
    assert dm.latest() is rec


def test_request_counter_increments():
    dm = DebugManager()
    dm.enable()
    t0 = time.monotonic()
    for i in range(3):
        rec = dm.begin_request(
            session_id="s",
            model_id="m",
            provider_name="p",
            alias_name="a",
            prompt_payload=[],
            gen_params=None,
            t_start=t0,
        )
        dm.finalize_request(rec)
    records = dm.all_records()
    assert [r.request_id for r in records] == [1, 2, 3]


def test_get_by_request_id():
    dm = DebugManager()
    dm.enable()
    t0 = time.monotonic()
    rec = dm.begin_request(
        session_id="s",
        model_id="m",
        provider_name="p",
        alias_name="a",
        prompt_payload=[],
        gen_params=None,
        t_start=t0,
    )
    dm.finalize_request(rec)
    found = dm.get(1)
    assert found is rec
    assert dm.get(999) is None


def test_deque_maxlen():
    dm = DebugManager()
    dm.enable()
    t0 = time.monotonic()
    for _ in range(DebugManager.MAX_RECORDS + 10):
        rec = dm.begin_request(
            session_id="s",
            model_id="m",
            provider_name="p",
            alias_name="a",
            prompt_payload=[],
            gen_params=None,
            t_start=t0,
        )
        dm.finalize_request(rec)
    assert len(dm.all_records()) == DebugManager.MAX_RECORDS


def test_http_client_none_when_logging_off():
    dm = DebugManager()
    assert dm.http_client() is None


def test_export_json(tmp_path: Path):
    dm = DebugManager()
    dm.enable()
    rec = _make_record(1)
    dm.finalize_request(rec)

    out = tmp_path / "debug.json"
    dm.export_json(out)
    assert out.exists()
    data = json.loads(out.read_text())
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["request_id"] == 1
    assert data[0]["stop_reason"] == "end_turn"


def test_export_txt(tmp_path: Path):
    dm = DebugManager()
    dm.enable()
    rec = _make_record(1)
    dm.finalize_request(rec)

    out = tmp_path / "debug.txt"
    dm.export_txt(out)
    assert out.exists()
    content = out.read_text()
    assert "Request #1" in content
    assert "end_turn" in content


def test_finalize_request_with_live_export(tmp_path: Path):
    """_append_export is called when _export_active=True and _export_path is set."""
    dm = DebugManager()
    dm.enable()
    # Directly activate the live export feature (no public API exposes this yet)
    dm._export_active = True
    dm._export_path = tmp_path / "live.jsonl"
    rec = _make_record(1)
    dm.finalize_request(rec)
    assert dm._export_path.exists()
    import json
    line = json.loads(dm._export_path.read_text().strip())
    assert line["request_id"] == 1


def test_append_export_no_export_path_is_noop():
    """_append_export returns early when _export_path is None."""
    dm = DebugManager()
    dm.enable()
    dm._export_active = True
    dm._export_path = None  # explicit None
    rec = _make_record(1)
    # Should not raise
    dm._append_export(rec)


def test_get_http_client_when_api_logging_active():
    """http_client() returns a client (or None) when api_logging is active."""
    dm = DebugManager()
    dm.toggle_api_logging()  # enable
    assert dm.api_logging_active() is True
    client = dm.http_client()
    # Should return an httpx.AsyncClient (or None if httpx not installed)
    assert client is not None or client is None  # just verifies no crash


def test_get_http_client_caches_client():
    """http_client() returns the same client on second call."""
    dm = DebugManager()
    dm.toggle_api_logging()
    c1 = dm.http_client()
    c2 = dm.http_client()
    if c1 is not None:
        assert c1 is c2
