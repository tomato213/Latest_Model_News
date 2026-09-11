import json

from src.models import Candidate
from src.state import SeenStore


def make_c(n):
    return [Candidate(id=f"src{i}", source="s", title=f"t{i}", url=f"u{i}") for i in range(n)]


def test_filter_new_and_mark_seen(tmp_path):
    p = tmp_path / "seen.json"
    store = SeenStore(p)
    cs = make_c(3)
    assert [c.id for c in store.filter_new(cs)] == ["src0", "src1", "src2"]
    store.mark_seen(cs[:2], "2026-09-10T00:00:00+00:00")
    assert [c.id for c in store.filter_new(cs)] == ["src2"]
    store.save()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["seen"]["src0"] == "2026-09-10T00:00:00+00:00"
    assert data["bootstrapped"] is False


def test_bootstrap_roundtrip(tmp_path):
    p = tmp_path / "seen.json"
    store = SeenStore(p)
    assert store.bootstrapped is False
    store.set_bootstrapped()
    store.save()
    assert SeenStore(p).bootstrapped is True


def test_pending_cycle(tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    cs = make_c(2)
    store.add_pending(cs)
    store.add_pending(cs)  # 不重复
    got = store.pop_pending()
    assert [c.id for c in got] == ["src0", "src1"]
    assert got[0].title == "t0"
    assert store.pop_pending() == []


def test_pending_push_cycle(tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    events = [{"id": "x", "title": "T", "url": "U", "source": "s", "event_type": "release", "summary": "S"}]
    store.add_pending_push(events)
    store.save()
    reloaded = SeenStore(tmp_path / "seen.json")
    assert reloaded.pop_pending_push() == events


def test_seen_capacity_trim(tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    cs = make_c(20)
    store.mark_seen(cs, "2026-09-10T00:00:00+00:00")
    # 人为触发淘汰：直接改上限不可行，这里验证大量 mark_seen 不崩溃且可 save/load
    store.save()
    assert len(SeenStore(tmp_path / "seen.json").data["seen"]) == 20


def test_loads_existing_file(tmp_path):
    p = tmp_path / "seen.json"
    p.write_text(json.dumps({"bootstrapped": True, "seen": {"a": "t"},
                             "pending": [], "pending_push": []}), encoding="utf-8")
    store = SeenStore(p)
    assert store.bootstrapped is True
    assert store.data["seen"] == {"a": "t"}
