"""Tests for bin/watch. Run: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest bin/tests/test_watch.py -v"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BIN = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("watch", str(BIN / "watch"))
_spec = importlib.util.spec_from_loader("watch", _loader)
W = importlib.util.module_from_spec(_spec)
_loader.exec_module(W)

DEN = ZoneInfo("America/Denver")


def at(s):
    return datetime.fromisoformat(s).replace(tzinfo=DEN)


CFG_MD = """# Machine config

## Available Tools

### Work board (`board` skill)
- Board page: <Notion page URL or id>
- Slack user id: U_ME
- Email: mail tools, mailbox me@example.com
- Watch-slack state file: {tmp}/req-ts.txt <!-- optional -->

### Watches (`watch` skill)
<!-- FILL IN: values for the watch skill. -->
- Registry: {tmp}/watches.json
- Time zone: America/Denver <!-- IANA name -->
- Tick interval: 5m
- Quiet hours: 19:00-08:00; weekends: quiet
- Business hours: 08:00-18:00
- Connectors: slack mcp__slack__, email mcp__mail__
- Requests channel: C_REQ
- Dagster: https://example.invalid/graphql, env file {tmp}/.env, token var DAGSTER_TOKEN
- Deploy rules: <!-- one line per repo -->
  - acme/app: branch prod
  - acme/web: workflow deploy on main
  - acme/lib: release-tag

### Finalize PR (`/pr`)
- Not: part of either section
"""

PR_SPEC = {"kind": "pr", "target": {"repo": "acme/app", "number": 7}, "expect": "green and approved"}


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.cfg_path = self.tmp / "CLAUDE.md"
        self.cfg_path.write_text(CFG_MD.format(tmp=self.tmp))
        self.reg_path = self.tmp / "watches.json"
        self.state_file = self.tmp / "req-ts.txt"
        self.cfg = W.load_config(self.cfg_path)
        self.reg = {"version": 1, "owner": None, "last_tick": None, "next_id": 1, "watches": []}

    def cli(self, *args, stdin=None):
        env = dict(os.environ)
        env.pop("WATCH_NOW", None)
        env.update(
            WATCH_REGISTRY=str(self.reg_path),
            WATCH_CONFIG=str(self.cfg_path),
            PYTHONDONTWRITEBYTECODE="1",
        )
        return subprocess.run(
            [sys.executable, str(BIN / "watch"), *args],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
        )

    def read_reg(self):
        return json.loads(self.reg_path.read_text())


class ConfigTests(Base):
    def test_load_config_parses_both_sections(self):
        self.assertEqual(self.cfg["tick"], timedelta(minutes=5))
        self.assertEqual(self.cfg["self_ids"], {"U_ME", "me@example.com"})
        self.assertEqual(self.cfg["requests"]["user"], "U_ME")
        self.assertTrue(self.cfg["requests"]["state_file"].endswith("req-ts.txt"))
        self.assertEqual(self.cfg["deploy_rules"]["acme/web"], {"type": "workflow", "name": "deploy", "branch": "main"})
        self.assertEqual(self.cfg["tz"], DEN)

    def test_load_config_other_values(self):
        self.assertEqual(self.cfg["registry"], str(self.tmp / "watches.json"))
        self.assertEqual(self.cfg["quiet"]["start"].strftime("%H:%M"), "19:00")
        self.assertEqual(self.cfg["quiet"]["end"].strftime("%H:%M"), "08:00")
        self.assertTrue(self.cfg["quiet"]["weekends"])
        self.assertEqual(self.cfg["business"]["end"].strftime("%H:%M"), "18:00")
        self.assertEqual(self.cfg["connectors"], {"slack": "mcp__slack__", "email": "mcp__mail__"})
        self.assertEqual(self.cfg["requests"]["channel"], "C_REQ")
        self.assertEqual(
            self.cfg["dagster"],
            {"url": "https://example.invalid/graphql", "env_file": str(self.tmp / ".env"), "token_var": "DAGSTER_TOKEN"},
        )
        self.assertEqual(self.cfg["deploy_rules"]["acme/app"], {"type": "branch", "name": "prod"})
        self.assertEqual(self.cfg["deploy_rules"]["acme/lib"], {"type": "release-tag"})
        self.assertEqual(len(self.cfg["deploy_rules"]), 3)

    def test_missing_time_zone_is_an_error(self):
        text = "\n".join(l for l in CFG_MD.format(tmp=self.tmp).splitlines() if "Time zone" not in l)
        self.cfg_path.write_text(text)
        with self.assertRaises(W.WatchError):
            W.load_config(self.cfg_path)

    def test_placeholder_time_zone_is_an_error(self):
        self.cfg_path.write_text(CFG_MD.format(tmp=self.tmp).replace("Time zone: America/Denver", "Time zone: <America/Denver>"))
        with self.assertRaises(W.WatchError):
            W.load_config(self.cfg_path)

    def test_requests_channel_without_state_file_is_an_error(self):
        text = "\n".join(l for l in CFG_MD.format(tmp=self.tmp).splitlines() if "Watch-slack state file" not in l)
        self.cfg_path.write_text(text)
        with self.assertRaises(W.WatchError):
            W.load_config(self.cfg_path)

    def test_parse_duration(self):
        self.assertEqual(W.parse_duration("5m"), timedelta(minutes=5))
        self.assertEqual(W.parse_duration("2h"), timedelta(hours=2))
        self.assertEqual(W.parse_duration("30s"), timedelta(seconds=30))
        self.assertEqual(W.parse_duration("1d"), timedelta(days=1))
        with self.assertRaises(W.WatchError):
            W.parse_duration("soon")

    def test_parse_deploy_rule_grammar(self):
        self.assertEqual(W.parse_deploy_rule("release-tag"), {"type": "release-tag"})
        self.assertEqual(W.parse_deploy_rule("branch prod"), {"type": "branch", "name": "prod"})
        with self.assertRaises(W.WatchError):
            W.parse_deploy_rule("tag v1")


class AddTests(Base):
    def test_add_fills_kind_defaults(self):
        wid = W.add_watch(self.reg, {"kind": "dagster-run", "target": {"run_id": "r1"}}, at("2026-10-28T10:00"), self.cfg)
        w = self.reg["watches"][0]
        self.assertEqual((wid, w["every"], w["expires"], w["quiet"], w["state"]["status"]), ("w-1", "5m", "until-terminal", False, "armed"))

    def test_add_rejects_unknown_kind_and_missing_target_keys(self):
        with self.assertRaises(W.WatchError):
            W.add_watch(self.reg, {"kind": "cron", "target": {}}, at("2026-10-28T10:00"), self.cfg)
        with self.assertRaises(W.WatchError):
            W.add_watch(self.reg, {"kind": "pr", "target": {"repo": "acme/app"}}, at("2026-10-28T10:00"), self.cfg)
        self.assertEqual(self.reg["watches"], [])

    def test_add_is_idempotent_for_same_target(self):
        a = W.add_watch(self.reg, dict(PR_SPEC), at("2026-10-28T10:00"), self.cfg)
        b = W.add_watch(self.reg, dict(PR_SPEC), at("2026-10-28T10:05"), self.cfg)
        self.assertEqual(a, b)
        self.assertEqual(len(self.reg["watches"]), 1)

    def test_add_after_stop_creates_new_row(self):
        a = W.add_watch(self.reg, dict(PR_SPEC), at("2026-10-28T10:00"), self.cfg)
        W.update_watch(self.reg, a, at("2026-10-28T10:01"), self.cfg, status="stopped")
        b = W.add_watch(self.reg, dict(PR_SPEC), at("2026-10-28T10:05"), self.cfg)
        self.assertNotEqual(a, b)

    def test_slack_add_without_cursor_starts_at_add_time(self):
        W.add_watch(self.reg, {"kind": "slack-thread", "target": {"channel": "C1", "thread_ts": "1.0"}}, at("2026-10-28T10:00"), self.cfg)
        self.assertEqual(float(self.reg["watches"][0]["state"]["cursor"]), at("2026-10-28T10:00").timestamp())

    def test_slack_add_with_cursor_keeps_it(self):
        W.add_watch(self.reg, {"kind": "slack-dm", "target": {"channel": "D1"}, "cursor": "123.456"}, at("2026-10-28T10:00"), self.cfg)
        self.assertEqual(self.reg["watches"][0]["state"]["cursor"], "123.456")

    def test_email_add_requires_cursor(self):
        with self.assertRaises(W.WatchError):
            W.add_watch(self.reg, {"kind": "email-thread", "target": {"thread_id": "t1"}}, at("2026-10-28T10:00"), self.cfg)

    def test_requests_first_add_starts_at_now_and_writes_state_file(self):
        self.assertFalse(self.state_file.exists())
        W.add_watch(self.reg, {"kind": "requests-channel", "target": {"channel": "C_REQ", "user": "U_ME"}}, at("2026-10-28T10:00"), self.cfg)
        cursor = self.reg["watches"][0]["state"]["cursor"]
        self.assertEqual(float(cursor), at("2026-10-28T10:00").timestamp())
        self.assertEqual(self.state_file.read_text().strip(), cursor)

    def test_requests_add_reads_existing_state_file(self):
        self.state_file.write_text("555.000100\n")
        W.add_watch(self.reg, {"kind": "requests-channel", "target": {"channel": "C_REQ", "user": "U_ME"}}, at("2026-10-28T10:00"), self.cfg)
        self.assertEqual(self.reg["watches"][0]["state"]["cursor"], "555.000100")


class UpdateTests(Base):
    def add_slack(self, cursor="100.0"):
        return W.add_watch(
            self.reg,
            {"kind": "slack-thread", "target": {"channel": "C1", "thread_ts": "1.0"}, "cursor": cursor},
            at("2026-10-28T10:00"),
            self.cfg,
        )

    def test_update_fire_filters_self_messages(self):
        wid = self.add_slack("100.0")
        now = at("2026-10-28T10:10")
        w = W.update_watch(self.reg, wid, now, self.cfg, messages=[{"author": "U_ME", "ts": "200.0"}])
        self.assertEqual(w["state"]["status"], "armed")
        self.assertEqual(w["state"]["cursor"], "200.0")
        w = W.update_watch(self.reg, wid, now, self.cfg, messages=[{"author": "U_X", "ts": "300.0", "text": "yes"}])
        self.assertEqual(w["state"]["status"], "fired")
        self.assertEqual(w["state"]["result"]["messages"][0]["author"], "U_X")
        self.assertEqual(w["state"]["cursor"], "300.0")
        self.assertIsNotNone(w["state"]["fired_at"])

    def test_update_ignores_messages_at_or_below_cursor(self):
        wid = self.add_slack("300.0")
        w = W.update_watch(self.reg, wid, at("2026-10-28T10:10"), self.cfg, messages=[{"author": "U_X", "ts": "250.0"}])
        self.assertEqual(w["state"]["status"], "armed")
        self.assertEqual(w["state"]["cursor"], "300.0")

    def test_requests_channel_fires_on_self_and_holds_cursor(self):
        self.state_file.write_text("100.0")
        wid = W.add_watch(self.reg, {"kind": "requests-channel", "target": {"channel": "C_REQ", "user": "U_ME"}}, at("2026-10-28T10:00"), self.cfg)
        now = at("2026-10-28T10:10")
        w = W.update_watch(
            self.reg, wid, now, self.cfg,
            messages=[{"author": "U_ME", "ts": "200.0"}, {"author": "U_X", "ts": "210.0"}],
        )
        self.assertEqual(w["state"]["status"], "fired")
        self.assertEqual(w["state"]["result"]["messages"], [{"author": "U_ME", "ts": "200.0"}])
        self.assertEqual(w["state"]["cursor"], "100.0")
        self.assertEqual(self.state_file.read_text().strip(), "100.0")
        w = W.update_watch(self.reg, wid, now, self.cfg, cursor="200.0", status="armed")
        self.assertEqual(w["state"]["cursor"], "200.0")
        self.assertEqual(self.state_file.read_text().strip(), "200.0")

    def test_cursor_never_moves_backward(self):
        self.assertEqual(W.advance_cursor("slack-thread", "300.5", "200.1"), "300.5")
        self.assertEqual(W.advance_cursor("pr", "a|b", "c|d"), "c|d")
        self.assertEqual(W.advance_cursor("slack-dm", None, "2.0"), "2.0")
        self.assertEqual(W.advance_cursor("email-thread", "m1", None), "m1")

    def test_filter_self(self):
        msgs = [{"author": "U_ME"}, {"author": "me@example.com"}, {"author": "U_X"}]
        self.assertEqual(W.filter_self(msgs, self.cfg["self_ids"]), [{"author": "U_X"}])

    def test_checked_and_error_counters(self):
        wid = self.add_slack()
        now = at("2026-10-28T10:10")
        w = W.update_watch(self.reg, wid, now, self.cfg, error="boom")
        w = W.update_watch(self.reg, wid, now, self.cfg, error="boom again")
        self.assertEqual((w["state"]["errors"], w["state"]["note"]), (2, "boom again"))
        self.assertIsNone(w["state"]["last_ok_check"])
        w["state"]["dispatched_at"] = "x"
        w["state"]["stale_raised"] = True
        w = W.update_watch(self.reg, wid, now, self.cfg, checked=True)
        s = w["state"]
        self.assertEqual((s["errors"], s["checks"], s["dispatched_at"], s["stale_raised"]), (0, 1, None, False))
        self.assertEqual(s["last_ok_check"], s["last_check"])

    def test_update_merge_records_words_time_and_head(self):
        now = at("2026-10-28T10:10")
        wid = W.add_watch(self.reg, dict(PR_SPEC), at("2026-10-28T10:00"), self.cfg)
        w = W.update_watch(self.reg, wid, now, self.cfg, merge="merge when green", head="abc")
        self.assertEqual(
            w["on_fire"]["merge"],
            {"words": "merge when green", "at": now.astimezone(timezone.utc).isoformat(), "head_sha": "abc"},
        )
        with self.assertRaises(W.WatchError):
            W.update_watch(self.reg, wid, now, self.cfg, merge="merge it")
        sid = self.add_slack()
        with self.assertRaises(W.WatchError):
            W.update_watch(self.reg, sid, now, self.cfg, merge="merge it", head="abc")

    def test_update_board_line_and_unknown_id(self):
        wid = self.add_slack()
        w = W.update_watch(self.reg, wid, at("2026-10-28T10:10"), self.cfg, board_line="- [ ] ask")
        self.assertEqual(w["board_line"], "- [ ] ask")
        with self.assertRaises(W.WatchError):
            W.update_watch(self.reg, "w-99", at("2026-10-28T10:10"), self.cfg, checked=True)


class CliTests(Base):
    def test_pause_resume_stop(self):
        self.assertEqual(self.cli("add", "--json", json.dumps(PR_SPEC)).returncode, 0)
        r = self.cli("add", stdin=json.dumps({"kind": "dagster-run", "target": {"run_id": "r1"}}))
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "w-2"))
        self.assertEqual(self.cli("pause").returncode, 0)
        self.assertEqual([w["state"]["status"] for w in self.read_reg()["watches"]], ["paused", "paused"])
        self.assertEqual(self.cli("resume").returncode, 0)
        self.assertEqual([w["state"]["status"] for w in self.read_reg()["watches"]], ["armed", "armed"])
        self.assertEqual(self.cli("stop", "w-1").returncode, 0)
        self.assertEqual([w["state"]["status"] for w in self.read_reg()["watches"]], ["stopped", "armed"])

    def test_add_from_file_and_status(self):
        spec_file = self.tmp / "spec.json"
        spec_file.write_text(json.dumps(PR_SPEC))
        self.assertEqual(self.cli("add", "--file", str(spec_file)).stdout.strip(), "w-1")
        r = self.cli("status", "w-1")
        self.assertEqual(json.loads(r.stdout)["target"], {"repo": "acme/app", "number": 7})
        self.assertEqual(json.loads(self.cli("status").stdout)["next_id"], 2)

    def test_update_via_cli(self):
        self.cli("add", "--json", json.dumps({"kind": "slack-thread", "target": {"channel": "C1", "thread_ts": "1.0"}, "cursor": "100.0"}))
        msgs = self.tmp / "msgs.json"
        msgs.write_text(json.dumps([{"author": "U_X", "ts": "150.0", "text": "hi"}]))
        r = self.cli("--now", "2026-10-28T10:10:00-06:00", "update", "w-1", "--checked", "--messages-file", str(msgs), "--draft", "d1")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.read_reg()["watches"][0]["state"]
        self.assertEqual((s["status"], s["cursor"], s["draft"], s["checks"]), ("fired", "150.0", "d1", 1))
        self.assertEqual(s["last_check"], "2026-10-28T16:10:00+00:00")
        r = self.cli("update", "w-9", "--checked")
        self.assertEqual(r.returncode, 2)

    def test_save_is_atomic_and_leaves_no_temp(self):
        self.assertEqual(self.cli("add", "--json", json.dumps(PR_SPEC)).returncode, 0)
        self.assertEqual(self.cli("add", "--json", json.dumps({"kind": "dagster-run", "target": {"run_id": "r1"}})).returncode, 0)
        names = {p.name for p in self.tmp.iterdir() if p.name.startswith("watches")}
        self.assertEqual(names, {"watches.json", "watches.json.lock"})
        self.assertEqual(len(self.read_reg()["watches"]), 2)

    def test_corrupt_registry_is_not_overwritten(self):
        self.reg_path.write_text("{not json")
        r = self.cli("add", "--json", json.dumps(PR_SPEC))
        self.assertEqual(r.returncode, 2)
        self.assertIn(str(self.reg_path), r.stderr)
        self.assertEqual(self.reg_path.read_text(), "{not json")

    def test_failed_command_writes_nothing(self):
        self.cli("add", "--json", json.dumps(PR_SPEC))
        before = self.reg_path.read_text()
        r = self.cli("update", "w-1", "--merge", "merge it")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.reg_path.read_text(), before)

    def test_list_shows_next_check_and_tick_not_running(self):
        now = at("2026-10-28T10:00")
        W.add_watch(self.reg, dict(PR_SPEC), now - timedelta(minutes=30), self.cfg)
        w = self.reg["watches"][0]
        w["state"]["last_check"] = w["state"]["last_ok_check"] = (now - timedelta(minutes=10)).astimezone(timezone.utc).isoformat()
        self.reg["owner"] = "master"
        self.reg["last_tick"] = (now - timedelta(minutes=20)).astimezone(timezone.utc).isoformat()
        out = W.format_list(self.reg, self.cfg, now)
        self.assertIn('w-1 pr armed next 10:05 last ok 09:50 "green and approved"', out)
        self.assertIn("tick: last 09:40 by master", out)
        self.assertIn("tick not running", out)
        self.reg_path.write_text(json.dumps(self.reg))
        r = self.cli("--now", now.isoformat(), "list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("tick not running", r.stdout)

    def test_list_fresh_tick_and_never_checked(self):
        now = at("2026-10-28T10:00")
        W.add_watch(self.reg, dict(PR_SPEC, expect="x" * 80), now, self.cfg)
        W.add_watch(self.reg, {"kind": "dagster-run", "target": {"run_id": "r1"}}, now, self.cfg)
        W.update_watch(self.reg, "w-2", now, self.cfg, status="stopped")
        self.reg["owner"] = "master"
        self.reg["last_tick"] = (now - timedelta(minutes=4)).astimezone(timezone.utc).isoformat()
        out = W.format_list(self.reg, self.cfg, now)
        self.assertIn('last ok never "' + "x" * 60 + '"', out)
        self.assertNotIn("w-2", out)
        self.assertNotIn("tick not running", out)


if __name__ == "__main__":
    unittest.main()
