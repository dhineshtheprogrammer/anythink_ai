"""Tests for smart/store.py."""

from anythink.smart.models import SpecialistResponse
from anythink.smart.store import TemporaryResponseStore


def _make_resp(slot: int = 1, response: str = "ok") -> SpecialistResponse:
    return SpecialistResponse(
        slot=slot,
        category="general",
        model_alias="local",
        sub_question="Q",
        response=response,
        quality_score=75,
        retry_count=0,
        duration_s=0.1,
    )


def test_store_starts_empty():
    store = TemporaryResponseStore()
    assert len(store) == 0
    assert store.all() == []


def test_add_and_retrieve():
    store = TemporaryResponseStore()
    r1 = _make_resp(slot=1, response="answer 1")
    r2 = _make_resp(slot=2, response="answer 2")
    store.add(r1)
    store.add(r2)
    assert len(store) == 2
    entries = store.all()
    assert entries[0].response == "answer 1"
    assert entries[1].response == "answer 2"


def test_all_returns_copy():
    store = TemporaryResponseStore()
    store.add(_make_resp())
    entries = store.all()
    entries.clear()
    assert len(store) == 1


def test_clear():
    store = TemporaryResponseStore()
    store.add(_make_resp())
    store.add(_make_resp(slot=2))
    store.clear()
    assert len(store) == 0
    assert store.all() == []


def test_order_preserved():
    store = TemporaryResponseStore()
    for i in range(5):
        store.add(_make_resp(slot=i, response=str(i)))
    for i, entry in enumerate(store.all()):
        assert entry.response == str(i)
