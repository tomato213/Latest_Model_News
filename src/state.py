import json
from pathlib import Path

from .models import Candidate

SCHEMA = {"bootstrapped": False, "seen": {}, "pending": [], "pending_push": []}
MAX_SEEN = 20000
TRIM_COUNT = 5000


class SeenStore:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = json.loads(json.dumps(SCHEMA))

    @property
    def bootstrapped(self):
        return self.data["bootstrapped"]

    def set_bootstrapped(self):
        self.data["bootstrapped"] = True

    def filter_new(self, candidates):
        return [c for c in candidates if c.id not in self.data["seen"]]

    def mark_seen(self, candidates, iso_now):
        for c in candidates:
            self.data["seen"][c.id] = iso_now
        if len(self.data["seen"]) > MAX_SEEN:
            for k in sorted(self.data["seen"], key=self.data["seen"].get)[:TRIM_COUNT]:
                del self.data["seen"][k]

    def add_pending(self, candidates):
        ids = {d["id"] for d in self.data["pending"]}
        self.data["pending"] += [c.to_dict() for c in candidates if c.id not in ids]

    def pop_pending(self):
        items = self.data["pending"]
        self.data["pending"] = []
        return [Candidate.from_dict(d) for d in items]

    def add_pending_push(self, events):
        self.data["pending_push"] += events

    def pop_pending_push(self):
        items = self.data["pending_push"]
        self.data["pending_push"] = []
        return items

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
