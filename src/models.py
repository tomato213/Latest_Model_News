from dataclasses import asdict, dataclass, field


@dataclass
class Candidate:
    id: str
    source: str
    title: str
    url: str
    published_at: str | None = None
    extra: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d["id"],
            source=d["source"],
            title=d["title"],
            url=d["url"],
            published_at=d.get("published_at"),
            extra=d.get("extra", ""),
        )
