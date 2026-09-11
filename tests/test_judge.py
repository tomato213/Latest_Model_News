from unittest.mock import patch

from src.judge import judge, keyword_judgment
from src.models import Candidate


def _c(i, title):
    return Candidate(id=i, source="openai", title=title, url="u")


def test_empty_input():
    assert judge([]) == []


def test_llm_success_path():
    cs = [_c("a", "Introducing GPT-6"), _c("b", "Benchmark leaderboard drama")]
    llm_resp = {"choices": [{"message": {"content":
        '[{"id":"a","is_event":true,"event_type":"release","summary":"GPT-6发布"},'
        '{"id":"b","is_event":false,"event_type":"","summary":"榜单帖"}]'}}]}
    with patch("src.judge.post_json", return_value=llm_resp) as p:
        out = judge(cs)
    body = p.call_args.args[1]
    assert body["model"] == "deepseek-flash"
    assert "Introducing GPT-6" in body["messages"][1]["content"]
    assert out[0] == {"id": "a", "is_event": True, "event_type": "release",
                      "summary": "GPT-6发布", "decided": True}
    assert out[1]["decided"] is True and out[1]["is_event"] is False


def test_llm_json_with_code_fences():
    cs = [_c("a", "Kimi K4 open weights released")]
    llm_resp = {"choices": [{"message": {"content":
        '```json\n[{"id":"a","is_event":true,"event_type":"open_weights","summary":"K4开源"}]\n```'}}]}
    with patch("src.judge.post_json", return_value=llm_resp):
        out = judge(cs)
    assert out[0]["event_type"] == "open_weights"


def test_llm_missing_entry_gets_keyword_fallback():
    cs = [_c("a", "Qwen3.9 released"), _c("b", "Weekly discussion thread")]
    llm_resp = {"choices": [{"message": {"content": '[{"id":"a","is_event":true,"event_type":"release","summary":"ok"}]'}}]}
    with patch("src.judge.post_json", return_value=llm_resp):
        out = judge(cs)
    assert out[0]["decided"] is True
    assert out[1]["decided"] is False  # 关键词不命中 → pending


def test_api_failure_falls_back():
    from src.http_client import HttpClientError
    cs = [_c("a", "DeepSeek-V5 weights 开源发布"), _c("b", "Leaderboard benchmark results")]
    with patch("src.judge.post_json", side_effect=HttpClientError("api down")):
        out = judge(cs)
    assert out[0]["decided"] is True and out[0]["is_event"] is True
    assert out[1]["decided"] is False  # 负面词 → 不判


def test_keyword_judgment_rules():
    hit = keyword_judgment(_c("x", "GLM-5.4 new model release"))
    assert hit and hit["is_event"] is True
    assert keyword_judgment(_c("y", "AI policy announcement")) is None  # 无关键词
    assert keyword_judgment(_c("z", "Model benchmark leaderboard")) is None  # 负面词
