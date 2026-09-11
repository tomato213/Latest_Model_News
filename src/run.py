import sys
from datetime import datetime, timezone

from .config import (EVENTS_MD_PATH, MAX_CANDIDATES_PER_JUDGE,
                     SKIP_OLDER_THAN_HOURS, STATE_PATH)
from .judge import judge
from .models import Candidate
from .notify import push_events
from .sources import ALL_SOURCES
from .state import SeenStore


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _is_stale(c, now):
    if not c.published_at:
        return False
    try:
        pub = datetime.fromisoformat(c.published_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    age_h = (now - pub).total_seconds() / 3600
    return age_h > SKIP_OLDER_THAN_HOURS or age_h < -2


def collect_candidates():
    out = []
    for name, fetch in ALL_SOURCES:
        try:
            items = fetch()
            print(f"[{name}] {len(items)} candidates")
            out.extend(items)
        except Exception as exc:
            print(f"[{name}] FAILED: {exc}")
    return out


def append_events_md(events, iso_now):
    lines = [f"\n## {iso_now}", ""]
    for e in events:
        lines.append(
            f"- **[{e['title']}]({e['url']})** — {e.get('event_type')} — "
            f"{e.get('summary', '')} ({e['source']})"
        )
    with open(EVENTS_MD_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    now = datetime.now(timezone.utc)
    store = SeenStore(STATE_PATH)

    candidates = collect_candidates()
    fresh = store.filter_new(candidates)
    now_stale = [c for c in fresh if _is_stale(c, now)]
    fresh = [c for c in fresh if not _is_stale(c, now)]
    store.mark_seen(now_stale, _now_iso())

    if not store.bootstrapped:
        store.mark_seen(candidates, _now_iso())
        store.set_bootstrapped()
        store.save()
        print(f"bootstrap: marked {len(candidates)} seen, no push")
        return 0

    to_judge = fresh[:MAX_CANDIDATES_PER_JUDGE]
    store.add_pending(fresh[MAX_CANDIDATES_PER_JUDGE:])

    all_c = to_judge + store.pop_pending()
    # DEVIATION from brief: skip judge on empty batch (judge() with no
    # candidates is a no-op anyway; avoids spurious LLM/mock calls).
    judgments = judge(all_c) if all_c else []
    by_id = {c.id: c for c in all_c}

    events, undecided = [], []
    for j in judgments:
        if j["decided"] and j["is_event"]:
            events.append({**by_id[j["id"]].to_dict(),
                           "event_type": j["event_type"], "summary": j["summary"]})
        elif not j["decided"]:
            undecided.append(by_id[j["id"]])

    keep_ids = {c.id for c in undecided}
    store.mark_seen([c for c in all_c if c.id not in keep_ids], _now_iso())
    store.add_pending(undecided)

    # DEVIATION from brief: defer push while undecided candidates remain —
    # events (plus existing pending_push) wait and are pushed next round,
    # so nothing is lost and no empty/partial push happens.
    if undecided:
        store.add_pending_push(events)
    else:
        all_events = events + store.pop_pending_push()
        if push_events(all_events):
            append_events_md(all_events, _now_iso())
        else:
            store.add_pending_push(all_events)

    store.save()
    print(f"done: {len(events)} new events, {len(undecided)} pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
