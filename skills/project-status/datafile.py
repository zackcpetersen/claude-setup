"""Shared read-modify-write for projects.json, so job.py, add_oneoff.py and apply_events.py never lose each other's edits.

    with locked_json(path) as data:
        data["as_of"] = ...           # changes are written atomically when the block ends normally

Raise NoWrite inside the block to leave the file as it was (a dry run, nothing to do). Any other error also
leaves the file untouched. The lock is an exclusive flock on `<path>.lock`, held from the read to the write.
"""
import contextlib
import fcntl
import json
import os
import pathlib


class NoWrite(Exception):
    """Raise inside locked_json to skip the write without an error."""


def write_atomic(path, data):
    path = pathlib.Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


@contextlib.contextmanager
def locked_json(path):
    path = pathlib.Path(path)
    with open(path.with_name(path.name + ".lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text())
        try:
            yield data
        except NoWrite:
            return
        write_atomic(path, data)
