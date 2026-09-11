import pytest


@pytest.fixture
def fx():
    def _load(name):
        from pathlib import Path
        return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")
    return _load


def test_parse_rss2(fx):
    from src.rss_util import parse_feed
    items = parse_feed(fx("openai_rss.xml"))
    assert len(items) == 2
    assert items[0]["title"] == "Introducing GPT-5.3"
    assert items[0]["link"] == "https://openai.com/index/introducing-gpt-5-3/"
    assert items[0]["published"] == "2026-09-09T10:00:00+00:00"


def test_parse_atom(fx):
    from src.rss_util import parse_feed
    items = parse_feed(fx("reddit_atom.xml"))
    assert len(items) == 2
    assert items[0]["link"] == "https://www.reddit.com/r/LocalLLaMA/comments/1abc/qwen38_27b_released/"
    assert items[0]["published"] == "2026-09-10T08:00:00+00:00"
    assert items[1]["title"] == "Weekly benchmark discussion thread"


def test_unsupported_root_raises():
    from src.rss_util import parse_feed
    with pytest.raises(ValueError):
        parse_feed("<html><body>hi</body></html>")


def test_empty_item_without_link_dropped():
    from src.rss_util import parse_feed
    text = '<?xml version="1.0"?><rss version="2.0"><channel><item><title>no link</title></item></channel></rss>'
    assert parse_feed(text) == []
