from ..config import GH_REPOS
from ..http_client import get_json
from ..models import Candidate


def fetch():
    out = []
    for repo in GH_REPOS:
        try:
            rels = get_json(f"https://api.github.com/repos/{repo}/releases?per_page=5")
        except Exception:
            continue
        for r in rels:
            out.append(Candidate(
                id=f"github:{repo}:{r['id']}",
                source="github",
                title=f"{repo} {r.get('name') or r.get('tag_name')}",
                url=r.get("html_url", f"https://github.com/{repo}/releases"),
                published_at=r.get("published_at"),
            ))
    return out
