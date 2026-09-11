from unittest.mock import patch

from src import notify

EVENTS = [
    {"id": "a", "source": "anthropic", "title": "Claude Opus 6",
     "url": "https://www.anthropic.com/news/x", "published_at": "2026-09-09",
     "event_type": "release", "summary": "Claude Opus 6 发布"},
]


def test_build_message_contains_markdown_link_and_type():
    title, desp = notify.build_message(EVENTS)
    assert title == "🤖 模型发布动态 (1条)"
    assert "[Claude Opus 6](https://www.anthropic.com/news/x)" in desp
    assert "新模型发布" in desp
    assert "Claude Opus 6 发布" in desp
    assert "anthropic" in desp


def test_push_events_empty_is_true():
    assert notify.push_events([]) is True


def test_push_events_calls_post_form():
    with patch("src.notify.post_form", return_value="ok") as p, \
         patch.dict("os.environ", {"DRY_RUN": ""}):
        assert notify.push_events(EVENTS) is True
        url = p.call_args.args[0]
        assert url.startswith("https://sctapi.ftqq.com/") and url.endswith(".send")
        data = p.call_args.args[1]
        assert "title" in data and "desp" in data


def test_push_events_dry_run_skips_http():
    with patch("src.notify.post_form") as p, \
         patch.dict("os.environ", {"DRY_RUN": "1"}):
        assert notify.push_events(EVENTS) is True
        p.assert_not_called()


def test_push_events_failure_returns_false():
    with patch("src.notify.post_form", side_effect=Exception("bad key")), \
         patch.dict("os.environ", {"DRY_RUN": "", "SERVERCHAN_SENDKEY": "SCT_x"}):
        assert notify.push_events(EVENTS) is False
