import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

ATOM = "{http://www.w3.org/2005/Atom}"


def _to_utc_iso(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_date(s):
    if not s or not s.strip():
        return None
    s = s.strip()
    try:
        return _to_utc_iso(parsedate_to_datetime(s))
    except (TypeError, ValueError):
        pass
    try:
        return _to_utc_iso(datetime.fromisoformat(s.replace("Z", "+00:00")))
    except ValueError:
        return None


def parse_feed(text):
    root = ET.fromstring(text)
    items = []
    if root.tag == "rss":
        for el in root.iter("item"):
            items.append({
                "title": (el.findtext("title") or "").strip(),
                "link": (el.findtext("link") or "").strip(),
                "published": _parse_date(el.findtext("pubDate")),
            })
    elif root.tag == f"{ATOM}feed":
        for el in root.iter(f"{ATOM}entry"):
            link = ""
            for le in el.findall(f"{ATOM}link"):
                if le.get("rel") in (None, "alternate"):
                    link = le.get("href", "")
                    break
            items.append({
                "title": (el.findtext(f"{ATOM}title") or "").strip(),
                "link": link,
                "published": _parse_date(el.findtext(f"{ATOM}published") or el.findtext(f"{ATOM}updated")),
            })
    else:
        raise ValueError(f"unsupported feed root: {root.tag}")
    return [i for i in items if i["link"]]
