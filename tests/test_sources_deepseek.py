from pathlib import Path
from unittest.mock import patch

from src.sources import deepseek

FIX = Path(__file__).parent / "fixtures"


def test_fetch_extracts_slugs_and_titles():
    index = (FIX / "deepseek_updates.html").read_text(encoding="utf-8")
    page = (FIX / "deepseek_news_page.html").read_text(encoding="utf-8")

    def fake_get_text(url, headers=None):
        if "updates" in url:
            return index
        return page  # any news page

    with patch("src.sources.deepseek.get_text", side_effect=fake_get_text):
        out = deepseek.fetch()

    by_id = {c.id: c for c in out}
    assert set(by_id) == {"deepseek:news260910", "deepseek:news260813", "deepseek:news0725"}
    assert by_id["deepseek:news260910"].title == "DeepSeek-V4.1-Flash: Smarter, Faster, More Efficient"
    assert by_id["deepseek:news260910"].url == "https://api-docs.deepseek.com/news/news260910/"
    assert by_id["deepseek:news260910"].published_at is None


def test_fetch_title_fallback_on_page_error():
    index = (FIX / "deepseek_updates.html").read_text(encoding="utf-8")
    from src.http_client import HttpClientError

    def fake_get_text(url, headers=None):
        if "updates" in url:
            return index
        raise HttpClientError("page down")

    with patch("src.sources.deepseek.get_text", side_effect=fake_get_text):
        out = deepseek.fetch()
    c = {x.id: x for x in out}["deepseek:news260910"]
    assert c.title == "news260910"  # slug fallback
