import json
from unittest.mock import patch

import pytest

import src.run as run
from src.models import Candidate


def _c(i, title, published="2026-09-10T00:00:00+00:00"):
    return Candidate(id=i, source="openai", title=title, url=f"https://x/{i}",
                     published_at=published)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "STATE_PATH", tmp_path / "state" / "seen.json")
    monkeypatch.setattr(run, "EVENTS_MD_PATH", tmp_path / "events.md")
    return tmp_path


def _fake_sources(*batches):
    """按返回批次构造 ALL_SOURCES：[(name, fetch), ...]"""
    return [(f"src{i}", (lambda b: (lambda: b))(b)) for i, b in enumerate(batches)]


def test_first_run_bootstrap_no_push(env):
    with patch.object(run, "ALL_SOURCES", _fake_sources([_c("a", "New model X")])), \
         patch.object(run, "judge") as j, \
         patch.object(run, "push_events") as p:
        assert run.main() == 0
        j.assert_not_called()
        p.assert_not_called()
    data = json.loads((env / "state" / "seen.json").read_text(encoding="utf-8"))
    assert data["bootstrapped"] is True
    assert "a" in data["seen"]


def test_event_flow_push_and_events_md(env):
    # 预置已 bootstrap 的状态，候选 a 为已见，b 为新事件
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {"a": "2026-09-09T00:00:00+00:00"},
                              "pending": [], "pending_push": []}), encoding="utf-8")
    with patch.object(run, "ALL_SOURCES", _fake_sources([_c("a", "old"), _c("b", "Kimi K4 released")])), \
         patch.object(run, "judge", return_value=[
             {"id": "b", "is_event": True, "event_type": "open_weights",
              "summary": "Kimi K4 开源", "decided": True}]), \
         patch.object(run, "push_events", return_value=True) as p:
        assert run.main() == 0
    p.assert_called_once()
    events = p.call_args.args[0]
    assert events[0]["id"] == "b" and events[0]["summary"] == "Kimi K4 开源"
    md = (env / "events.md").read_text(encoding="utf-8")
    assert "Kimi K4" in md
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert "b" in data["seen"] and data["pending"] == []


def test_push_failure_keeps_pending_push(env):
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {},
                              "pending": [], "pending_push": []}), encoding="utf-8")
    with patch.object(run, "ALL_SOURCES", _fake_sources([_c("b", "New GPT")])), \
         patch.object(run, "judge", return_value=[
             {"id": "b", "is_event": True, "event_type": "release",
              "summary": "GPT发布", "decided": True}]), \
         patch.object(run, "push_events", return_value=False):
        run.main()
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert len(data["pending_push"]) == 1
    # 下轮推送成功
    with patch.object(run, "ALL_SOURCES", _fake_sources([])), \
         patch.object(run, "judge", return_value=[]), \
         patch.object(run, "push_events", return_value=True) as p:
        run.main()
    p.assert_called_once()
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["pending_push"] == []


def test_undecided_goes_back_to_pending(env):
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {},
                              "pending": [], "pending_push": []}), encoding="utf-8")
    with patch.object(run, "ALL_SOURCES", _fake_sources([_c("u", "Some announcement")])), \
         patch.object(run, "judge", return_value=[
             {"id": "u", "is_event": False, "event_type": "", "summary": "", "decided": False}]), \
         patch.object(run, "push_events") as p:
        run.main()
    p.assert_not_called()
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert [d["id"] for d in data["pending"]] == ["u"]
    assert "u" not in data["seen"]


def test_stale_candidates_marked_seen_without_judging(env):
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {},
                              "pending": [], "pending_push": []}), encoding="utf-8")
    old = _c("old", "Old release", published="2026-01-01T00:00:00+00:00")
    with patch.object(run, "ALL_SOURCES", _fake_sources([old])), \
         patch.object(run, "judge") as j, \
         patch.object(run, "push_events"):
        run.main()
    j.assert_not_called()
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert "old" in data["seen"]


def test_source_failure_does_not_block(env):
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {},
                              "pending": [], "pending_push": []}), encoding="utf-8")

    def boom():
        raise RuntimeError("blocked")

    with patch.object(run, "ALL_SOURCES", [("bad", boom), ("good", lambda: [_c("n", "New")])]), \
         patch.object(run, "judge", return_value=[
             {"id": "n", "is_event": False, "event_type": "", "summary": "", "decided": True}]), \
         patch.object(run, "push_events", return_value=True) as p:
        assert run.main() == 0
    p.assert_called_once()  # push_events([]) 也会调用，验证主流程走到最后
    # Final-review fix: 空事件轮次不再向 events.md 追加空小节
    assert not (env / "events.md").exists()


def test_judge_batch_capped_fresh_overflow_to_pending(env):
    """Final-review fix: 超过 MAX_CANDIDATES_PER_JUDGE 的新候选溢出到 pending，
    judge 只收到恰好 MAX 条。"""
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {},
                              "pending": [], "pending_push": []}), encoding="utf-8")
    batch = [_c(f"c{i}", f"New model {i}") for i in range(5)]
    with patch.object(run, "MAX_CANDIDATES_PER_JUDGE", 2), \
         patch.object(run, "ALL_SOURCES", _fake_sources(batch)), \
         patch.object(run, "judge", return_value=[
             {"id": "c0", "is_event": False, "event_type": "", "summary": "", "decided": True},
             {"id": "c1", "is_event": False, "event_type": "", "summary": "", "decided": True},
         ]) as j, \
         patch.object(run, "push_events", return_value=True):
        assert run.main() == 0
    assert [c.id for c in j.call_args.args[0]] == ["c0", "c1"]
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert [d["id"] for d in data["pending"]] == ["c2", "c3", "c4"]


def test_judge_batch_cap_includes_pending_overflow(env):
    """Final-review fix: fresh + pending 合计超限时，总批次封顶在 MAX，
    溢出项（含回流 pending）留在 pending，不丢。"""
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({
        "bootstrapped": True, "seen": {},
        "pending": [{"id": "p1", "source": "s", "title": "pending one", "url": "u1"}],
        "pending_push": []}), encoding="utf-8")
    batch = [_c(f"c{i}", f"New model {i}") for i in range(3)]
    with patch.object(run, "MAX_CANDIDATES_PER_JUDGE", 2), \
         patch.object(run, "ALL_SOURCES", _fake_sources(batch)), \
         patch.object(run, "judge", return_value=[
             {"id": "c0", "is_event": False, "event_type": "", "summary": "", "decided": True},
             {"id": "c1", "is_event": False, "event_type": "", "summary": "", "decided": True},
         ]) as j, \
         patch.object(run, "push_events", return_value=True):
        assert run.main() == 0
    assert [c.id for c in j.call_args.args[0]] == ["c0", "c1"]
    data = json.loads(sp.read_text(encoding="utf-8"))
    # c2 (fresh 溢出) 与 p1 (pending 溢出) 都留在 pending，顺序保持
    assert [d["id"] for d in data["pending"]] == ["c2", "p1"]
    # 溢出条目未被误标 seen，下轮仍可判
    assert "c2" not in data["seen"] and "p1" not in data["seen"]


def test_duplicate_id_across_fresh_and_pending_judged_once(env):
    """Final-review fix: 同一 id 同时出现在 fresh 与 pending 时只判一次。"""
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({
        "bootstrapped": True, "seen": {},
        "pending": [{"id": "d1", "source": "openai", "title": "dup announcement",
                     "url": "https://x/d1", "published_at": "2026-09-10T00:00:00+00:00"}],
        "pending_push": []}), encoding="utf-8")
    with patch.object(run, "ALL_SOURCES", _fake_sources([_c("d1", "dup announcement")])), \
         patch.object(run, "judge", return_value=[
             {"id": "d1", "is_event": True, "event_type": "release",
              "summary": "dup 发布", "decided": False}]) as j, \
         patch.object(run, "push_events", return_value=True):
        assert run.main() == 0
    assert len(j.call_args.args[0]) == 1
    assert j.call_args.args[0][0].id == "d1"


def test_events_deferred_while_undecided_then_pushed_next_round(env):
    """Sanctioned deviation: 有未判定条目时事件延迟推送，下轮补推。"""
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {},
                              "pending": [], "pending_push": []}), encoding="utf-8")
    # 第 N 轮：1 条事件 + 1 条未判定 → 不推送
    with patch.object(run, "ALL_SOURCES", _fake_sources([_c("e", "Kimi K4 released"),
                                                         _c("u", "ambiguous")])), \
         patch.object(run, "judge", return_value=[
             {"id": "e", "is_event": True, "event_type": "release",
              "summary": "K4 发布", "decided": True},
             {"id": "u", "is_event": False, "event_type": "", "summary": "", "decided": False},
         ]), \
         patch.object(run, "push_events") as p:
        assert run.main() == 0
        p.assert_not_called()
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert len(data["pending_push"]) == 1 and data["pending_push"][0]["id"] == "e"
    assert "e" in data["seen"] and "u" not in data["seen"]
    assert [d["id"] for d in data["pending"]] == ["u"]
    # 第 N+1 轮：无未判定 → 补推延迟事件
    with patch.object(run, "ALL_SOURCES", _fake_sources([])), \
         patch.object(run, "judge", return_value=[]), \
         patch.object(run, "push_events", return_value=True) as p:
        assert run.main() == 0
    p.assert_called_once()
    assert [ev["id"] for ev in p.call_args.args[0]] == ["e"]
    md = (env / "events.md").read_text(encoding="utf-8")
    assert "Kimi K4" in md
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["pending_push"] == []
