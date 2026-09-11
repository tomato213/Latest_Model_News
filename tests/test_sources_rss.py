from unittest.mock import patch

import pytest


@pytest.fixture
def fx():
    def _load(name):
        from pathlib import Path
        return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")
    return _load


def test_openai_fetch(fx):
    from src.sources import openai
    with patch("src.sources.openai.get_text", return_value=fx("openai_rss.xml")):
        out = openai.fetch()
    assert len(out) == 2
    assert out[0].id == "openai:https://openai.com/index/introducing-gpt-5-3"
    assert out[0].source == "openai"
    assert out[0].title == "Introducing GPT-5.3"
    assert out[0].published_at == "2026-09-09T10:00:00+00:00"


def test_qwen_fetch(fx):
    from src.sources import qwen
    with patch("src.sources.qwen.get_text", return_value=fx("openai_rss.xml")):  # RSS2 结构相同
        out = qwen.fetch()
    assert out[0].source == "qwen"
    assert out[0].id.startswith("qwen:https://")


def test_reddit_fetch(fx):
    from src.sources import reddit
    with patch("src.sources.reddit.get_text", return_value=fx("reddit_atom.xml")):
        out = reddit.fetch()
    assert len(out) == 2
    assert out[0].source == "reddit"
    assert out[0].id.endswith("qwen38_27b_released")
    assert "Qwen3.8-27B released" in out[0].title


def test_fetch_propagates_http_error():
    from src.http_client import HttpClientError
    from src.sources import openai
    with patch("src.sources.openai.get_text", side_effect=HttpClientError("down")):
        try:
            openai.fetch()
            assert False, "should raise"
        except HttpClientError:
            pass
