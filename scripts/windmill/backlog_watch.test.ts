// bun test scripts/windmill
import { expect, test } from "bun:test";
import { decide, hostProblems, problems } from "./backlog_watch";

const now = Date.parse("2026-11-26T07:30:00Z");
const ago = (min: number) => new Date(now - min * 60000).toISOString();

test("names waiting work, long runs and failing schedules", () => {
  // The queue as seen 2026-11-26 07:24Z: Rebex image steps and the per-minute down alert waiting behind them.
  const queue = [
    { id: "a", script_path: "f/rebex_image/host_step", running: false, scheduled_for: ago(6) },
    { id: "b", script_path: "f/rebex_image/host_step", running: false, scheduled_for: ago(18) },
    { id: "c", script_path: "f/fld_ops/down_alert", running: false, scheduled_for: ago(7) },
    { id: "d", script_path: "f/fld_ops/cleanup_hourly", running: false, scheduled_for: ago(-45) }, // next hour: fine
    { id: "e", script_path: "f/ops/job_failed_notice", running: false, scheduled_for: ago(4) }, // under 5 min: fine
    { id: "f", script_path: "f/fld_ops/cleanup_hourly", running: true, scheduled_for: ago(80), started_at: ago(70) },
    { id: "g", script_path: "f/rebex_image/host_step", running: true, scheduled_for: ago(20), started_at: ago(15) },
  ];
  const runs = {
    "f/fld_ops/cleanup_hourly_schedule": [{ success: false }, { success: false, canceled: true }, { success: false }, { success: false }],
    "f/sweep/board_checks": [{ success: true }, { success: false }, { success: false }],
    "f/usage/daily_report": [{ success: false }, { success: false }], // too few runs to call it a streak
  };
  expect(problems(queue, runs, now)).toEqual({
    "wait:f/rebex_image/host_step": "f/rebex_image/host_step: 2 waiting for a worker, the oldest 18 min",
    "wait:f/fld_ops/down_alert": "f/fld_ops/down_alert: 1 waiting for a worker, the oldest 7 min",
    "long:f": "f/fld_ops/cleanup_hourly has been running 70 min",
    "fail:f/fld_ops/cleanup_hourly_schedule": "f/fld_ops/cleanup_hourly_schedule: its last 3 runs failed",
  });
  expect(problems([], {}, now)).toEqual({});
});

test("mails once a problem lasts two checks, again only for something new, a reminder, and once when clear", () => {
  const one = { "wait:f/a": "f/a: 3 waiting for a worker, the oldest 9 min" };
  let r = decide({}, one, now);
  expect(r.mail).toBeNull(); // a single check is not yet a backlog
  r = decide(r.next, one, now + 300e3);
  expect(r.mail?.subject).toBe("Work is piling up: 1 problem");
  expect(r.mail?.body).toContain("- f/a: 3 waiting for a worker, the oldest 9 min (new)");
  r = decide(r.next, one, now + 600e3);
  expect(r.mail).toBeNull(); // unchanged: no repeat
  const two = { ...one, "wait:f/x": "f/x: 1 waiting for a worker, the oldest 6 min" };
  r = decide(r.next, two, now + 900e3);
  expect(r.mail).toBeNull(); // the new one has lasted only one check
  r = decide(r.next, two, now + 1200e3);
  expect(r.mail?.subject).toBe("Work is piling up: 2 problems");
  expect(r.mail?.body).toContain("- f/x: 1 waiting for a worker, the oldest 6 min (new)");
  expect(r.mail?.body).not.toContain("9 min (new)");
  r = decide(r.next, two, now + 1200e3 + 6 * 3600e3);
  expect(r.mail?.subject).toBe("Work is piling up: 2 problems"); // 6 h reminder
  r = decide(r.next, {}, now + 7 * 3600e3);
  expect(r.mail?.subject).toBe("Queues and Macs are clear again");
  r = decide(r.next, {}, now + 7 * 3600e3 + 300e3);
  expect(r.mail).toBeNull();
});

test("no all-clear while a new problem is still being confirmed", () => {
  const a = { "wait:f/a": "f/a: 1 waiting for a worker, the oldest 9 min" };
  const b = { "wait:f/b": "f/b: 1 waiting for a worker, the oldest 6 min" };
  let r = decide(decide({}, a, now).next, a, now + 300e3);
  expect(r.mail?.subject).toBe("Work is piling up: 1 problem");
  r = decide(r.next, b, now + 600e3); // a cleared as b appeared
  expect(r.mail).toBeNull();
  r = decide(r.next, b, now + 900e3);
  expect(r.mail?.body).toContain("f/b: 1 waiting for a worker, the oldest 6 min (new)");
  r = decide(decide(r.next, {}, now + 1200e3).next, a, now + 1500e3);
  expect(r.mail).toBeNull();
  r = decide(decide(r.next, a, now + 1800e3).next, {}, now + 2100e3); // a returns, is mailed, then clears
  expect(r.mail?.subject).toBe("Queues and Macs are clear again");
});

test("passes on the host check's problems, and says when it goes quiet", () => {
  const send = { "send:rebex/rebex": "Your Send on the rebex/rebex page has waited 45 min for its agent to read it" };
  expect(hostProblems(JSON.stringify({ at: ago(8), problems: send }), now)).toEqual(send);
  expect(hostProblems({ at: ago(8), problems: {} }, now)).toEqual({});
  expect(hostProblems(JSON.stringify({ at: ago(40), problems: send }), now))
    .toEqual({ "host:quiet": "The M1Max host check (page Sends, Orca mail) has not reported for 40 min" });
  expect(Object.keys(hostProblems(null, now))).toEqual(["host:quiet"]);
  expect(Object.keys(hostProblems("not json", now))).toEqual(["host:quiet"]);
  expect(hostProblems({ at: "bad", problems: {} }, now))
    .toEqual({ "host:quiet": "The M1Max host check (page Sends, Orca mail) has not reported for an unknown number of min" });
});
