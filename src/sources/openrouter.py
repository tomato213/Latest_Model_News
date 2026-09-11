from datetime import datetime, timezone

from ..config import OPENROUTER_MODELS_URL
from ..http_client import get_json
from ..models import Candidate


def fetch():
    data = get_json(OPENROUTER_MODELS_URL).get("data", [])
    out = []
    for m in data:
        created = m.get("created")
        pub = datetime.fromtimestamp(created, tz=timezone.utc).isoformat() if created else None
        out.append(Candidate(
            id=f"openrouter:{m['id']}",
            source="openrouter",
            title=m.get("name") or m["id"],
            url=f"https://openrouter.ai/{m['id']}",
            published_at=pub,
            extra=f"context={m.get('context_length', '?')}",
        ))
    return out
