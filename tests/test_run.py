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


def test_first_run_bootstrap_no_push(env, capsys):
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
