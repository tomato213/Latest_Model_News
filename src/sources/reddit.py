from ..config import REDDIT_RSS_URL
from ..http_client import get_text
from ..models import Candidate
from ..rss_util import parse_feed


def fetch():
    return [
        Candidate(
            id=f"reddit:{item['link'].rstrip('/')}",
            source="reddit",
            title=item["title"],
            url=item["link"],
            published_at=item["published"],
        )
        for item in parse_feed(get_text(REDDIT_RSS_URL))
    ]
