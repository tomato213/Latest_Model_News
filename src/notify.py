import os

from .config import SERVERCHAN_SENDKEY
from .http_client import post_form

TYPE_LABEL = {"release": "新模型发布", "open_weights": "权重开源", "major_update": "重大升级"}


def build_message(events):
    lines = []
    for e in events:
        label = TYPE_LABEL.get(e.get("event_type"), "动态")
        lines.append(
            f"**[{e['title']}]({e['url']})** — {label}\n\n"
            f"{e.get('summary', '')}\n\n"
            f"来源: {e['source']} | {e.get('published_at') or '时间未知'}\n"
        )
    return f"🤖 模型发布动态 ({len(events)}条)", "\n---\n".join(lines)


def push_events(events):
    if not events:
        return True
    title, desp = build_message(events)
    if os.environ.get("DRY_RUN"):
        print(f"[DRY_RUN] would push: {title}\n{desp}")
        return True
    if not SERVERCHAN_SENDKEY:
        print("WARN: no SERVERCHAN_SENDKEY, skip push")
        return False
    try:
        post_form(f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send",
                  {"title": title, "desp": desp})
        return True
    except Exception as exc:
        print(f"push failed: {exc}")
        return False
