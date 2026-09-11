from ..config import HF_API_BASE, HF_ORGS
from ..http_client import get_json
from ..models import Candidate


def fetch():
    out = []
    for org in HF_ORGS:
        try:
            rows = get_json(f"{HF_API_BASE}/models?author={org}&sort=createdAt&direction=-1&limit=15")
        except Exception:
            continue  # 本地被墙 / 瞬时失败：跳过该组织
        for r in rows:
            mid = r.get("id") or (f"{r.get('author')}/{r.get('modelId')}")
            out.append(Candidate(
                id=f"hf:{mid}",
                source="hf",
                title=mid,
                url=f"https://huggingface.co/{mid}",
                published_at=r.get("createdAt"),
                extra=f"downloads={r.get('downloads', '?')} likes={r.get('likes', '?')}",
            ))
    return out
