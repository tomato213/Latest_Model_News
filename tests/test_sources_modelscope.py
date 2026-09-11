import json
from pathlib import Path
from unittest.mock import patch

from src.sources import modelscope

FIX = json.loads((Path(__file__).parent / "fixtures" / "modelscope_search.json").read_text(encoding="utf-8"))


def test_fetch_filters_to_official_orgs():
    with patch("src.sources.modelscope.put_json", return_value=FIX) as p:
        out = modelscope.fetch()
    assert p.call_count == len(modelscope.MS_KEYWORDS)
    first_call = p.call_args_list[0]
    assert first_call.args[0] == modelscope.MS_SEARCH_URL
    assert first_call.args[1]["Name"] == "qwen"
    ids = [c.id for c in out]
    assert "modelscope:Qwen/Qwen3.8-Flash-Next" in ids
    assert "modelscope:unsloth/Qwen3.8-Flash-Next-GGUF" not in ids  # 非官方组织被过滤
    c = [c for c in out if c.id == "modelscope:Qwen/Qwen3.8-Flash-Next"][0]
    assert c.title == "千问3.8-Flash-Next"
    assert c.url == "https://modelscope.cn/models/Qwen/Qwen3.8-Flash-Next"
    assert c.published_at == "2026-09-10T03:34:14+00:00"  # 1789011254


def test_fetch_survives_search_failure():
    from src.http_client import HttpClientError
    with patch("src.sources.modelscope.put_json", side_effect=HttpClientError("down")):
        assert modelscope.fetch() == []
