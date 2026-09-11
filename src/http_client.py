import time

import requests

from .config import USER_AGENT


class HttpClientError(Exception):
    pass


def _headers(extra):
    h = {"User-Agent": USER_AGENT}
    if extra:
        h.update(extra)
    return h


def _request(fn, url, *, headers=None, timeout=25, **kw):
    last_exc = None
    for attempt in range(2):
        try:
            resp = fn(url, headers=_headers(headers), timeout=timeout, **kw)
            if not (200 <= resp.status_code < 300):
                raise HttpClientError(f"{url} -> HTTP {resp.status_code}")
            return resp
        except HttpClientError:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(2)
    raise HttpClientError(f"{url} failed after retry: {last_exc}")


def get_json(url, headers=None, timeout=25):
    return _request(requests.get, url, headers=headers, timeout=timeout).json()


def get_text(url, headers=None, timeout=25):
    return _request(requests.get, url, headers=headers, timeout=timeout).text


def put_json(url, payload, headers=None, timeout=25):
    resp = _request(requests.put, url, headers=headers, timeout=timeout, json=payload)
    return resp.json()


def post_json(url, payload, headers=None, timeout=25):
    resp = _request(requests.post, url, headers=headers, timeout=timeout, json=payload)
    return resp.json()


def post_form(url, data, headers=None, timeout=25):
    return _request(requests.post, url, headers=headers, timeout=timeout, data=data).text
