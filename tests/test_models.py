from src.models import Candidate


def test_candidate_roundtrip():
    c = Candidate(
        id="openai:https://openai.com/index/x",
        source="openai",
        title="Introducing GPT-5.3",
        url="https://openai.com/index/x",
        published_at="2026-09-09T10:00:00+00:00",
        extra="downloads=100",
    )
    d = c.to_dict()
    assert d["id"] == "openai:https://openai.com/index/x"
    assert d["source"] == "openai"
    assert d["extra"] == "downloads=100"
    c2 = Candidate.from_dict(d)
    assert c2 == c


def test_candidate_defaults():
    c = Candidate(id="hf:Qwen/Q", source="hf", title="Q", url="https://huggingface.co/Qwen/Q")
    assert c.published_at is None
    assert c.extra == ""
