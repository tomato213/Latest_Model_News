from unittest.mock import patch

from src.sources import github, hf, openrouter

HF_JSON = [
    {"id": "Qwen/Qwen3.9-72B", "createdAt": "2026-09-09T12:00:00.000Z",
     "downloads": 1200, "likes": 45, "pipeline_tag": "text-generation"},
    {"id": "Qwen/Qwen3.8-27B", "createdAt": "2026-09-01T12:00:00.000Z",
     "downloads": 99000, "likes": 1200},
]

OR_JSON = {"data": [
    {"id": "moonshotai/kimi-k4", "name": "MoonshotAI: Kimi K4",
     "created": 1789050000, "context_length": 256000},
    {"id": "openai/gpt-5.2", "name": "OpenAI: GPT-5.2",
     "created": 1787000000, "context_length": 400000},
]}

GH_JSON = [{"id": 123456, "name": "gpt-oss-120b-updates", "tag_name": "v2026.09",
            "html_url": "https://github.com/openai/gpt-oss/releases/tag/v2026.09",
            "published_at": "2026-09-08T00:00:00Z"}]


def test_hf_fetch_all_orgs():
    with patch("src.sources.hf.get_json", return_value=HF_JSON) as g:
        out = hf.fetch()
    assert g.call_count == len(__import__("src.config", fromlist=["HF_ORGS"]).HF_ORGS)
    by_id = {c.id: c for c in out}
    assert "hf:Qwen/Qwen3.9-72B" in by_id
    c = by_id["hf:Qwen/Qwen3.9-72B"]
    assert c.url == "https://huggingface.co/Qwen/Qwen3.9-72B"
    assert c.published_at == "2026-09-09T12:00:00.000Z"
    assert "downloads=1200" in c.extra


def test_hf_fetch_skips_failed_org():
    from src.http_client import HttpClientError
    with patch("src.sources.hf.get_json", side_effect=HttpClientError("blocked")):
        assert hf.fetch() == []


def test_openrouter_fetch():
    with patch("src.sources.openrouter.get_json", return_value=OR_JSON):
        out = openrouter.fetch()
    by_id = {c.id: c for c in out}
    c = by_id["openrouter:moonshotai/kimi-k4"]
    assert c.title == "MoonshotAI: Kimi K4"
    assert c.url == "https://openrouter.ai/moonshotai/kimi-k4"
    assert c.published_at == "2026-09-10T14:20:00+00:00"  # 1789050000


def test_github_fetch():
    with patch("src.sources.github.get_json", return_value=GH_JSON):
        out = github.fetch()
    c = out[0]
    assert c.id == "github:openai/gpt-oss:123456"
    assert "gpt-oss-120b-updates" in c.title
    assert c.published_at == "2026-09-08T00:00:00Z"
