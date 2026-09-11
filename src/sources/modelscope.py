from datetime import datetime, timezone

from ..config import MS_KEYWORDS, MS_ORG_MAP, MS_SEARCH_URL
from ..http_client import put_json
from ..models import Candidate


def fetch():
    out, seen = [], set()
    for kw in MS_KEYWORDS:
        try:
            d = put_json(MS_SEARCH_URL, {"Name": kw, "PageSize": 20, "PageNumber": 1})
        except Exception:
            continue
        orgs = MS_ORG_MAP.get(kw, set())
        for m in d.get("Data", {}).get("Model", {}).get("Models", []):
            path, name = m.get("Path"), m.get("Name")
            if not path or not name or path not in orgs:
                continue
            key = f"{path}/{name}"
            if key in seen:
                continue
            seen.add(key)
            ct = m.get("CreatedTime")
            pub = datetime.fromtimestamp(ct, tz=timezone.utc).isoformat() if ct else None
            out.append(Candidate(
                id=f"modelscope:{key}",
                source="modelscope",
                title=(m.get("ChineseName") or name),
                url=f"https://modelscope.cn/models/{key}",
                published_at=pub,
            ))
    return out
