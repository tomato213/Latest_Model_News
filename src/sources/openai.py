from ..config import OPENAI_RSS_URL
from ..http_client import get_text
from ..models import Candidate
from ..rss_util import parse_feed


def fetch():
    return [
        Candidate(
            id=f"openai:{item['link'].rstrip('/')}",
            source="openai",
            title=item["title"],
            url=item["link"],
            published_at=item["published"],
        )
        for item in parse_feed(get_text(OPENAI_RSS_URL))
    ]
