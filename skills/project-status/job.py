#!/usr/bin/env python3
"""Record progress on a long job (a backfill, a big export) in a project status data file.

  job.py projects.json set <project_id> "<label>" --done N --total N [--unit files] [--per-day N] [--eta YYYY-MM-DD]
  job.py projects.json done <project_id> "<label>"

`set` creates the job or updates only the fields given (the label matches case-insensitively) and stamps
`updated`. `done` removes the job and logs "Finished <label>" in the project's recent progress, dated in the
config's `tz` (config.json next to the data file, or --config; else this machine's zone).
Both set the file's `as_of`. Then rebuild the page with build.py. Exit 1 when the project or job is missing.
"""
import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

from datafile import NoWrite, locked_json

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python older than 3.9
    ZoneInfo = None


def parse_now(text):
    if not text:
        return datetime.now(timezone.utc)
    t = text.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    d = datetime.fromisoformat(t)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def stamp(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def config_tz(data_path, config_path):
    """The IANA zone from config.json (next to the data file unless given), or None for this machine's zone."""
    path = pathlib.Path(config_path) if config_path else pathlib.Path(data_path).with_name("config.json")
    try:
        name = (json.loads(path.read_text()) or {}).get("tz") or ""
        return ZoneInfo(name) if name and ZoneInfo else None
    except Exception:
        return None


def number(text):
    v = float(text)
    return int(v) if v.is_integer() else v


def eta_date(text):
    datetime.strptime(text, "%Y-%m-%d")
    return text


def find_job(jobs, label):
    want = label.strip().lower()
    return next((j for j in jobs if str(j.get("label") or "").strip().lower() == want), None)


def set_job(project, label, fields, now):
    """Create the job or update only the given fields (done, total, unit, per_day, eta); stamp `updated`.

    Numbers go through number() and eta through eta_date(), so event fields ("2.5", "60") are stored like CLI ones.
    A bad value raises ValueError before anything changes.
    """
    fields = dict(fields)
    for k in ("done", "total", "per_day"):
        if fields.get(k) is not None:
            fields[k] = number(str(fields[k]))
    if fields.get("eta") is not None:
        fields["eta"] = eta_date(str(fields["eta"]))
    jobs = project.setdefault("jobs", [])
    job = find_job(jobs, label)
    if job is None:
        job = {"label": label}
        jobs.append(job)
    for k in ("done", "total", "unit", "per_day", "eta"):
        if fields.get(k) is not None:
            job[k] = fields[k]
    job["updated"] = stamp(now)
    return job


def finish_job(project, label, now, tz, day=None):
    """Remove the job and log "Finished <label>" dated `day` (else now in tz). The removed job, or None if gone."""
    jobs = project.get("jobs") or []
    job = find_job(jobs, label)
    if job is None:
        return None
    jobs.remove(job)
    row = {"date": day or now.astimezone(tz).date().isoformat(), "text": f"Finished {job.get('label')}"}
    rows = project.setdefault("recent_progress", [])
    if not any(r.get("date") == row["date"] and r.get("text") == row["text"] for r in rows):
        rows.append(row)  # a replay after a cursor reset must not log it twice
    return job


def main(argv=None):
    ap = argparse.ArgumentParser(description="Record progress on a long job.")
    ap.add_argument("data")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--now", help="fixed clock (ISO), for tests")
    common.add_argument("--config", help="config.json for tz (default: config.json next to the data file)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set", parents=[common])
    s.add_argument("project_id")
    s.add_argument("label")
    s.add_argument("--done", type=number)
    s.add_argument("--total", type=number)
    s.add_argument("--unit")
    s.add_argument("--per-day", type=number)
    s.add_argument("--eta", type=eta_date)
    f = sub.add_parser("done", parents=[common])
    f.add_argument("project_id")
    f.add_argument("label")
    a = ap.parse_args(argv)

    now = parse_now(a.now)
    with locked_json(pathlib.Path(a.data)) as data:
        project = next((p for p in data.get("projects") or [] if p.get("id") == a.project_id), None)
        if project is None:
            print(f"no project with id {a.project_id!r}", file=sys.stderr)
            raise NoWrite
        if a.cmd == "set":
            fields = {"done": a.done, "total": a.total, "unit": a.unit, "per_day": a.per_day, "eta": a.eta}
            job = set_job(project, a.label, fields, now)
            print(f"set: {job['label']} {job.get('done', '?')} of {job.get('total', '?')}")
        else:
            job = finish_job(project, a.label, now, config_tz(a.data, a.config))
            if job is None:
                print(f"no job {a.label!r} in {a.project_id}", file=sys.stderr)
                raise NoWrite
            print(f"done: {job.get('label')}")
        data["as_of"] = stamp(now)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
