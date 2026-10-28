"""Tests for bin/watch. Run: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest bin/tests/test_watch.py -v"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
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

    def test_backticked_values_are_unwrapped(self):
        text = (
            CFG_MD.format(tmp=self.tmp)
            .replace("Slack user id: U_ME", "Slack user id: `U_ME`")
            .replace(f"Watch-slack state file: {self.tmp}/req-ts.txt", f"Watch-slack state file: `{self.tmp}/req-ts.txt`")
            .replace("  - acme/app: branch prod", "  - `acme/app`: `branch prod`")
        )
        self.cfg_path.write_text(text)
        cfg = W.load_config(self.cfg_path)
        self.assertEqual(cfg["self_ids"], {"U_ME", "me@example.com"})
        self.assertEqual(cfg["requests"]["user"], "U_ME")
        self.assertEqual(cfg["requests"]["state_file"], str(self.tmp / "req-ts.txt"))
        self.assertEqual(cfg["deploy_rules"]["acme/app"], {"type": "branch", "name": "prod"})

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

    def test_report_on_paused_watch_keeps_cursor(self):
        wid = self.add_slack("100.0")
        now = at("2026-10-28T10:10")
        report = [{"author": "U_X", "ts": "300.0", "text": "yes"}]
        W.update_watch(self.reg, wid, now, self.cfg, status="paused")
        w = W.update_watch(self.reg, wid, now, self.cfg, messages=report)
        self.assertEqual((w["state"]["status"], w["state"]["cursor"]), ("paused", "100.0"))
        W.update_watch(self.reg, wid, now, self.cfg, status="armed")
        w = W.update_watch(self.reg, wid, now, self.cfg, messages=report)
        self.assertEqual((w["state"]["status"], w["state"]["cursor"]), ("fired", "300.0"))

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


def utc(dt):
    return dt.astimezone(timezone.utc).isoformat()


SLACK_SPEC = {"kind": "slack-thread", "target": {"channel": "C1", "thread_ts": "1.0"}, "cursor": "100.0"}


class TimeTests(Base):
    def test_quiet_overnight_window(self):
        for s, q in [("2026-10-27T22:00", True), ("2026-10-27T07:59", True), ("2026-10-27T08:00", False), ("2026-10-27T18:59", False)]:
            self.assertEqual(W.in_quiet_hours(at(s), self.cfg), q, s)

    def test_quiet_uses_config_zone_not_input_offset(self):
        self.assertTrue(W.in_quiet_hours(datetime(2026, 10, 28, 4, 0, tzinfo=timezone.utc), self.cfg))  # 22:00 in Denver
        self.assertFalse(W.in_quiet_hours(datetime(2026, 10, 28, 16, 0, tzinfo=timezone.utc), self.cfg))  # 10:00 in Denver

    def test_weekend_quiet_and_poll(self):
        self.assertTrue(W.in_quiet_hours(at("2026-10-31T12:00"), self.cfg))
        cfg = dict(self.cfg, quiet=dict(self.cfg["quiet"], weekends=False))
        self.assertFalse(W.in_quiet_hours(at("2026-10-31T12:00"), cfg))
        self.assertTrue(W.in_quiet_hours(at("2026-10-31T22:00"), cfg))

    def test_add_business_days_cases(self):
        self.assertEqual(W.add_business_days(at("2026-10-30T20:00"), 1, self.cfg), at("2026-11-03T08:00"))
        self.assertEqual(W.add_business_days(at("2026-10-31T10:00"), 1, self.cfg), at("2026-11-03T08:00"))
        self.assertEqual(W.add_business_days(at("2026-10-26T10:00"), 5, self.cfg), at("2026-11-02T10:00"))
        self.assertEqual(W.add_business_days(at("2026-10-27T06:00"), 1, self.cfg), at("2026-10-28T08:00"))

    def test_business_days_across_dst_end_keep_local_hour(self):
        r = W.add_business_days(at("2026-10-30T15:00"), 1, self.cfg)  # MDT, DST ends 2026-11-01
        self.assertEqual((r.astimezone(DEN).hour, r.utcoffset()), (15, timedelta(hours=-7)))

    def test_expiry_rules(self):
        created = at("2026-10-26T10:00")
        w = {"expires": "two-days", "created": utc(created), "target": {}}
        self.assertIsNone(W.expiry_state(w, created + timedelta(hours=47), self.cfg))
        self.assertEqual(W.expiry_state(w, created + timedelta(hours=48), self.cfg), "hard")
        w = {"expires": "until-terminal", "created": utc(created), "target": {"run_id": "r", "expected_hours": 2}}
        self.assertIsNone(W.expiry_state(w, created + timedelta(hours=2), self.cfg))
        self.assertEqual(W.expiry_state(w, created + timedelta(hours=2, minutes=1), self.cfg), "soft")
        w["target"] = {"run_id": "r"}
        self.assertIsNone(W.expiry_state(w, created + timedelta(days=30), self.cfg))
        for rule in ("until-closed", "never"):
            self.assertIsNone(W.expiry_state({"expires": rule, "created": utc(created), "target": {}}, created + timedelta(days=99), self.cfg))
        w = {"expires": "2026-10-27T12:00:00-06:00", "created": utc(created), "target": {}}
        self.assertIsNone(W.expiry_state(w, at("2026-10-27T11:59"), self.cfg))
        self.assertEqual(W.expiry_state(w, at("2026-10-27T12:00"), self.cfg), "hard")

    def test_add_rejects_naive_or_bad_times(self):
        with self.assertRaises(W.WatchError):
            W.add_watch(self.reg, dict(PR_SPEC, after="2026-10-28T11:00"), at("2026-10-28T10:00"), self.cfg)
        with self.assertRaises(W.WatchError):
            W.add_watch(self.reg, dict(PR_SPEC, expires="someday"), at("2026-10-28T10:00"), self.cfg)
        W.add_watch(self.reg, dict(PR_SPEC, after="2026-10-28T11:00:00-06:00"), at("2026-10-28T10:00"), self.cfg)
        self.assertEqual(self.reg["watches"][0]["after"], "2026-10-28T17:00:00+00:00")

    def test_short_error_masks_token(self):
        with mock.patch.dict(os.environ, {"DAGSTER_TOKEN": "sekret123"}):
            out = W.short_error(RuntimeError("bad auth sekret123 " + "x" * 200), self.cfg)
        self.assertNotIn("sekret123", out)
        self.assertTrue(out.startswith("RuntimeError: bad auth *** "))
        self.assertEqual(len(out), len("RuntimeError: ") + 120)


class TickTests(Base):
    def tick(self, s, **kw):
        kw.setdefault("session", "me")
        return W.tick(self.reg, self.cfg, at(s), **kw)

    def test_reply_expiry_soft_once_then_hard(self):
        W.add_watch(self.reg, dict(SLACK_SPEC), at("2026-10-26T10:00"), self.cfg)
        w = self.reg["watches"][0]
        r = self.tick("2026-10-27T10:01")
        self.assertEqual(r["expired"], [{"id": "w-1", "rule": "reply", "phase": "soft"}])
        self.assertEqual(W.cadence(w), timedelta(minutes=60))
        W.update_watch(self.reg, "w-1", at("2026-10-27T10:02"), self.cfg, checked=True)
        r = self.tick("2026-10-27T11:05")
        self.assertEqual(r["expired"], [])
        r = self.tick("2026-11-02T10:01")
        self.assertEqual(r["expired"], [{"id": "w-1", "rule": "reply", "phase": "hard"}])
        self.assertEqual(w["state"]["status"], "expired")
        r = self.tick("2026-11-02T10:06")
        self.assertEqual(r["expired"], [])

    def test_quiet_false_polls_at_night(self):
        W.add_watch(self.reg, {"kind": "dagster-run", "target": {"run_id": "r1"}}, at("2026-10-28T22:00"), self.cfg)
        W.add_watch(self.reg, dict(PR_SPEC), at("2026-10-28T22:00"), self.cfg)
        with mock.patch.object(W, "run_check", return_value=("RUNNING", None, {})) as rc:
            self.tick("2026-10-28T23:00")
        self.assertEqual([c.args[0]["id"] for c in rc.call_args_list], ["w-1"])

    def test_after_delays_first_check(self):
        W.add_watch(self.reg, dict(PR_SPEC, after="2026-10-28T11:00:00-06:00"), at("2026-10-28T10:00"), self.cfg)
        with mock.patch.object(W, "run_check", return_value=("p", None, {})) as rc:
            self.tick("2026-10-28T10:30")
            self.assertEqual(rc.call_count, 0)
            self.tick("2026-10-28T11:00")
            self.assertEqual(rc.call_count, 1)

    def test_script_check_fires_once_and_moves_cursor(self):
        W.add_watch(self.reg, dict(PR_SPEC, board_line="- [ ] pr 7"), at("2026-10-28T10:00"), self.cfg)
        with mock.patch.object(W, "run_check", return_value=("green|approved", "ready", {"urgent": True})):
            r = self.tick("2026-10-28T10:00")
        s = self.reg["watches"][0]["state"]
        self.assertEqual((s["status"], s["cursor"], s["checks"], s["result"]), ("fired", "green|approved", 1, {"urgent": True}))
        row = r["fired"][0]
        self.assertEqual((row["id"], row["event"], row["urgent"], row["board_line"]), ("w-1", "ready", True, "- [ ] pr 7"))
        self.assertEqual(set(row), {"id", "kind", "event", "result", "target", "expect", "reply_brief", "on_fire", "urgent", "board_line"})

    def test_same_fingerprint_does_not_fire(self):
        W.add_watch(self.reg, dict(PR_SPEC, cursor="same"), at("2026-10-28T10:00"), self.cfg)
        with mock.patch.object(W, "run_check", return_value=("same", "ready", {})):
            r = self.tick("2026-10-28T10:00")
        self.assertEqual((r["fired"], self.reg["watches"][0]["state"]["status"]), ([], "armed"))

    def test_agent_watch_listed_once_then_stale_then_retried(self):
        W.add_watch(self.reg, dict(SLACK_SPEC), at("2026-10-28T09:59"), self.cfg)
        s = self.reg["watches"][0]["state"]
        r = self.tick("2026-10-28T10:00")
        self.assertEqual(r["due"]["slack"], [{"id": "w-1", "kind": "slack-thread", "target": {"channel": "C1", "thread_ts": "1.0"}, "cursor": "100.0"}])
        self.assertEqual(r["due"]["email"], [])
        r = self.tick("2026-10-28T10:05")
        self.assertEqual(r["due"]["slack"], [])
        r = self.tick("2026-10-28T10:11")
        self.assertEqual(r["stale"], [{"id": "w-1", "reason": "detect agent did not report"}])
        self.assertEqual(r["due"]["slack"], [])
        self.assertIsNone(s["dispatched_at"])
        self.assertEqual(s["errors"], 1)
        r = self.tick("2026-10-28T10:21")
        self.assertEqual([d["id"] for d in r["due"]["slack"]], ["w-1"])
        r = self.tick("2026-10-28T10:32")  # second silent agent: retried again, not raised again
        self.assertEqual(r["stale"], [])
        self.assertIsNone(s["dispatched_at"])
        r = self.tick("2026-10-28T10:42")
        self.assertEqual([d["id"] for d in r["due"]["slack"]], ["w-1"])

    def test_three_consecutive_errors_raise_stale_once(self):
        W.add_watch(self.reg, dict(PR_SPEC), at("2026-10-28T09:00"), self.cfg)
        stales = []
        with mock.patch.object(W, "run_check", side_effect=RuntimeError("boom")):
            for t in ("10:00", "10:15", "10:30", "10:45", "11:00"):
                stales.append(self.tick(f"2026-10-28T{t}")["stale"])
        self.assertEqual(stales, [[], [], [], [{"id": "w-1", "reason": "3 failed checks in a row: RuntimeError: boom"}], []])
        s = self.reg["watches"][0]["state"]
        self.assertEqual((s["errors"], s["last_ok_check"], s["status"]), (5, None, "armed"))
        with mock.patch.object(W, "run_check", return_value=("p", None, {})):
            self.tick("2026-10-28T11:15")
        self.assertEqual((s["errors"], s["stale_raised"]), (0, False))

    def test_fired_unhandled_timeouts(self):
        now = at("2026-10-28T12:00")
        pr = {"kind": "pr", "state": {"status": "fired", "fired_at": utc(now - timedelta(minutes=11)), "errors": 0, "dispatched_at": None}}
        self.assertEqual(W.stale_reason(pr, now), "fired but not handled")
        req = {"kind": "requests-channel", "state": {"status": "fired", "fired_at": utc(now - timedelta(minutes=30)), "errors": 0, "dispatched_at": None}}
        self.assertIsNone(W.stale_reason(req, now))
        req["state"]["fired_at"] = utc(now - timedelta(minutes=61))
        self.assertEqual(W.stale_reason(req, now), "fired but not handled")

    def test_long_gap_does_not_mass_stale(self):
        then = at("2026-10-27T23:05")
        W.add_watch(self.reg, dict(PR_SPEC), then, self.cfg)
        W.add_watch(self.reg, {"kind": "dagster-run", "target": {"run_id": "r1"}}, then, self.cfg)
        W.add_watch(self.reg, dict(SLACK_SPEC), then, self.cfg)
        for w in self.reg["watches"]:
            w["state"]["last_check"] = w["state"]["last_ok_check"] = utc(then)
        self.reg["owner"], self.reg["last_tick"] = "me", utc(then)
        with mock.patch.object(W, "run_check", return_value=("p", None, {})) as rc:
            r = self.tick("2026-10-28T08:05")
            self.assertEqual((r["stale"], r["expired"], r["fired"]), ([], [], []))
            self.assertEqual(sorted(c.args[0]["id"] for c in rc.call_args_list), ["w-1", "w-2"])
            self.assertEqual([d["id"] for d in r["due"]["slack"]], ["w-3"])
            r = self.tick("2026-10-28T08:06")
            self.assertEqual((r["stale"], r["due"]["slack"], rc.call_count), ([], [], 2))

    def test_paused_watch_is_not_checked(self):
        W.add_watch(self.reg, dict(PR_SPEC), at("2026-10-28T09:00"), self.cfg)
        W.update_watch(self.reg, "w-1", at("2026-10-28T09:00"), self.cfg, status="paused")
        with mock.patch.object(W, "run_check", return_value=("p", None, {})) as rc:
            self.tick("2026-10-28T10:00")
        self.assertEqual(rc.call_count, 0)

    def test_tick_refuses_other_owner_recent(self):
        self.reg["owner"], self.reg["last_tick"] = "other", at("2026-10-28T10:00").isoformat()
        with self.assertRaises(W.NotOwner):
            W.tick(self.reg, self.cfg, at("2026-10-28T10:05"), session="me")
        self.assertEqual(self.reg["last_tick"], at("2026-10-28T10:00").isoformat())

    def test_tick_take_overrides_and_old_owner_is_replaced(self):
        self.reg["owner"], self.reg["last_tick"] = "other", utc(at("2026-10-28T10:00"))
        W.tick(self.reg, self.cfg, at("2026-10-28T10:05"), session="me", take=True)
        self.assertEqual((self.reg["owner"], self.reg["last_tick"]), ("me", utc(at("2026-10-28T10:05"))))
        self.reg["owner"], self.reg["last_tick"] = "other", utc(at("2026-10-28T10:00"))
        W.tick(self.reg, self.cfg, at("2026-10-28T10:11"), session="me")
        self.assertEqual(self.reg["owner"], "me")


class TickCliTests(Base):
    def test_noop_tick_prints_nothing_and_only_touches_tick_fields(self):
        W.add_watch(self.reg, dict(PR_SPEC), at("2026-10-28T09:00"), self.cfg)
        w = self.reg["watches"][0]
        w["state"]["last_check"] = w["state"]["last_ok_check"] = utc(at("2026-10-28T10:00"))
        self.reg_path.write_text(json.dumps(self.reg))
        snapshot = self.read_reg()
        r = self.cli("--now", "2026-10-28T10:02:00-06:00", "tick", "--session", "me")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        after = self.read_reg()
        self.assertEqual((after["owner"], after["last_tick"]), ("me", "2026-10-28T16:02:00+00:00"))
        for key in ("owner", "last_tick"):
            after.pop(key)
            snapshot.pop(key)
        self.assertEqual(after, snapshot)

    def test_tick_with_news_prints_one_json_line(self):
        self.cli("--now", "2026-10-28T10:00:00-06:00", "add", "--json", json.dumps(SLACK_SPEC))
        r = self.cli("--now", "2026-10-28T10:00:00-06:00", "tick", "--session", "me")
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["due"]["slack"][0]["id"], "w-1")

    def test_cli_tick_refused_exits_3(self):
        self.reg["owner"], self.reg["last_tick"] = "other", utc(at("2026-10-28T10:00"))
        self.reg_path.write_text(json.dumps(self.reg))
        before = self.reg_path.read_text()
        r = self.cli("--now", "2026-10-28T10:04:00-06:00", "tick", "--session", "me")
        self.assertEqual((r.returncode, r.stdout), (3, ""))
        self.assertEqual(r.stderr, "tick refused: owned by other, last tick 10:00\n")
        self.assertEqual(self.reg_path.read_text(), before)
        r = self.cli("--now", "2026-10-28T10:04:00-06:00", "tick", "--take", "--session", "me")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_reg()["owner"], "me")

    def test_add_during_tick_is_not_lost(self):
        W.add_watch(self.reg, dict(PR_SPEC), at("2026-10-28T09:00"), self.cfg)
        self.reg_path.write_text(json.dumps(self.reg))
        env = dict(os.environ, WATCH_REGISTRY=str(self.reg_path), WATCH_CONFIG=str(self.cfg_path), PYTHONDONTWRITEBYTECODE="1")
        env.pop("WATCH_NOW", None)
        procs = []

        def slow_check(w, cfg):
            procs.append(subprocess.Popen(
                [sys.executable, str(BIN / "watch"), "add", "--json", json.dumps(SLACK_SPEC)],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ))
            time.sleep(0.5)
            return ("pending", None, {})

        with mock.patch.object(W, "run_check", side_effect=slow_check):
            rc = W.main(["--registry", str(self.reg_path), "--config", str(self.cfg_path),
                         "--now", "2026-10-28T10:00:00-06:00", "tick", "--session", "me"])
        self.assertEqual(rc, 0)
        self.assertEqual(procs[0].wait(timeout=10), 0)
        reg = self.read_reg()
        self.assertEqual([w["kind"] for w in reg["watches"]], ["pr", "slack-thread"])
        self.assertEqual(reg["watches"][0]["state"]["cursor"], "pending")
        self.assertEqual(reg["last_tick"], "2026-10-28T16:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
