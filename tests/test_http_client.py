from unittest.mock import MagicMock, patch

import pytest
import requests

from src import http_client
from src.http_client import HttpClientError


def _resp(status=200, json_data=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    r.text = text
    return r


def test_get_json_parses_and_sends_default_ua():
    with patch("src.http_client.requests.get", return_value=_resp(json_data={"ok": 1})) as g:
        assert http_client.get_json("https://x/y") == {"ok": 1}
        kwargs = g.call_args.kwargs
        assert kwargs["timeout"] == 25
        assert "model-news-tracker" in kwargs["headers"]["User-Agent"]


def test_get_json_merges_custom_headers():
    with patch("src.http_client.requests.get", return_value=_resp(json_data={})) as g:
        http_client.get_json("https://x", headers={"Authorization": "Bearer t"})
        assert g.call_args.kwargs["headers"]["Authorization"] == "Bearer t"
        assert "User-Agent" in g.call_args.kwargs["headers"]


def test_non_2xx_raises():
    with patch("src.http_client.requests.get", return_value=_resp(status=404)):
        with pytest.raises(HttpClientError, match="404"):
            http_client.get_text("https://x/404")


def test_retry_once_on_network_error_then_success():
    with patch("src.http_client.requests.get", side_effect=[requests.ConnectionError("boom"), _resp(json_data={})]), \
         patch("src.http_client.time.sleep") as s:
        assert http_client.get_json("https://x") == {}
        s.assert_called_once_with(2)


def test_both_attempts_fail_raises():
    with patch("src.http_client.requests.get", side_effect=requests.Timeout("t")), \
         patch("src.http_client.time.sleep"):
        with pytest.raises(HttpClientError):
            http_client.get_json("https://x")


def test_put_json_and_post_form():
    with patch("src.http_client.requests.put", return_value=_resp(json_data={"Code": 200})) as p:
        assert http_client.put_json("https://x", {"a": 1}) == {"Code": 200}
        p.call_args.kwargs["json"] == {"a": 1}
    with patch("src.http_client.requests.post", return_value=_resp(text="ok")) as p:
        assert http_client.post_form("https://x", {"title": "t"}) == "ok"
        assert p.call_args.kwargs["data"] == {"title": "t"}
