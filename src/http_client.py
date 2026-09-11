import time
from urllib.parse import urlsplit

import requests

from .config import USER_AGENT


def _host(url):
    # ServerChan 等 URL 含 SENDKEY 密钥，报错时只暴露 host，避免泄漏。
    return urlsplit(url).netloc


class HttpClientError(Exception):
    pass


def _headers(extra):
    h = {"User-Agent": USER_AGENT}
    if extra:
        h.update(extra)
    return h


def _request(fn, url, *, headers=None, timeout=25, want=None, **kw):
    last_exc = None
    for attempt in range(2):
        try:
            resp = fn(url, headers=_headers(headers), timeout=timeout, **kw)
            if not (200 <= resp.status_code < 300):
                raise HttpClientError(f"{_host(url)} -> HTTP {resp.status_code}")
            if want == "json":
                try:
                    return resp.json()
                except ValueError as exc:  # 含 requests.exceptions.JSONDecodeError
                    raise HttpClientError(f"{_host(url)} returned invalid JSON: {exc}") from exc
            if want == "text":
                return resp.text
            return resp
        except HttpClientError:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(2)
    raise HttpClientError(f"{_host(url)} failed after retry: {last_exc}")


def get_json(url, headers=None, timeout=25):
    return _request(requests.get, url, headers=headers, timeout=timeout, want="json")


def get_text(url, headers=None, timeout=25):
    return _request(requests.get, url, headers=headers, timeout=timeout, want="text")


def put_json(url, payload, headers=None, timeout=25):
    return _request(requests.put, url, headers=headers, timeout=timeout, want="json", json=payload)


def post_json(url, payload, headers=None, timeout=25):
    return _request(requests.post, url, headers=headers, timeout=timeout, want="json", json=payload)


def post_form(url, data, headers=None, timeout=25):
    return _request(requests.post, url, headers=headers, timeout=timeout, want="text", data=data)
