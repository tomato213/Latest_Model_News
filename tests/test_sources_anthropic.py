from pathlib import Path

from src.sources import anthropic

FIXTURE = Path(__file__).parent / "fixtures" / "anthropic_news.html"


def test_fetch_extracts_slug_title_date():
    with patch_text(FIXTURE.read_text(encoding="utf-8")):
        out = anthropic.fetch()
    by_id = {c.id: c for c in out}
    assert len(out) == 3  # duplicate slug skipped
    c = by_id["anthropic:introducing-claude-opus-6"]
    assert c.title == "Introducing Claude Opus 6"
    assert c.url == "https://www.anthropic.com/news/introducing-claude-opus-6"
    assert c.published_at == "2026-09-09T00:00:00+00:00"


def test_fetch_without_h4_and_date_falls_back():
    with patch_text(FIXTURE.read_text(encoding="utf-8")):
        out = anthropic.fetch()
    by_id = {c.id: c for c in out}
    c = by_id["anthropic:research-preview-no-date"]
    assert c.published_at is None
    assert "Research Preview No Date" in c.title  # slug fallback


def patch_text(text):
    from unittest.mock import patch
    return patch("src.sources.anthropic.get_text", return_value=text)
