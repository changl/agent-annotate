//native
// Windmill f/ops/backlog_watch (Chang, 2026-11-26: "alert and surface ... queues that are building up and not
// getting addressed"). Every 5 min on the native workers, so a full python queue cannot hold the watch back.
// Mails Chang when a problem lasts two checks, again only for something new or every 6 h while it lasts, and once
// when all is clear. No AI. Off: disable schedule f/ops/backlog_watch.
const STATE = "f/ops/backlog_watch_state";
const HOST = "f/ops/host_backlog"; // scripts/host_backlog.py on the M1 Max: page Sends and Orca queues Docker cannot see
const KEY = "f/fld_ops/sendgrid_api_key"; // the SendGrid key f/fld_ops/down_alert already mails Chang with
const TO = "changl@gmail.com";
export const LIMITS = { waitMin: 5, runMin: 60, failStreak: 3, confirmChecks: 2, remindHours: 6, hostQuietMin: 30 };

type Job = { id: string; script_path?: string; running: boolean; scheduled_for: string; started_at?: string | null };
type Run = { success: boolean; canceled?: boolean };
type State = { seen?: Record<string, number>; mailed?: string[]; mail_at?: number };

// A full worker pool shows as waiting work; the job token may not read workers/list (403), so no pool check.
export function problems(queue: Job[], runs: Record<string, Run[]>, now: number) {
  const out: Record<string, string> = {};
  const age = (t: string) => (now - Date.parse(t)) / 60000;
  const waiting: Record<string, number[]> = {};
  for (const j of queue) {
    if (!j.running && age(j.scheduled_for) > LIMITS.waitMin) (waiting[j.script_path ?? "?"] ??= []).push(age(j.scheduled_for));
    if (j.running && j.started_at && age(j.started_at) > LIMITS.runMin)
      out[`long:${j.id}`] = `${j.script_path} has been running ${Math.round(age(j.started_at))} min`;
  }
  for (const [path, ages] of Object.entries(waiting))
    out[`wait:${path}`] = `${path}: ${ages.length} waiting for a worker, the oldest ${Math.round(Math.max(...ages))} min`;
  for (const [schedule, last] of Object.entries(runs)) {
    const done = last.filter((r) => !r.canceled).slice(0, LIMITS.failStreak);
    if (done.length === LIMITS.failStreak && done.every((r) => !r.success))
      out[`fail:${schedule}`] = `${schedule}: its last ${LIMITS.failStreak} runs failed`;
  }
  return out;
}

export function hostProblems(raw: unknown, now: number): Record<string, string> {
  let host: { at?: string; problems?: Record<string, string> } = {};
  try { host = (typeof raw === "string" ? JSON.parse(raw) : raw) ?? {}; } catch { /* unreadable reads as quiet */ }
  const quiet = host.at ? Math.round((now - Date.parse(host.at)) / 60000) : null;
  if (quiet === null || quiet > LIMITS.hostQuietMin)
    return { "host:quiet": `The M1Max host check (page Sends, Orca mail) has not reported for ${quiet ?? "an unknown number of"} min` };
  return host.problems ?? {};
}

export function decide(state: State, current: Record<string, string>, now: number) {
  const seen: Record<string, number> = {};
  for (const k of Object.keys(current)) seen[k] = (state.seen?.[k] ?? 0) + 1;
  const confirmed = Object.keys(current).filter((k) => seen[k] >= LIMITS.confirmChecks).sort();
  const mailed = (state.mailed ?? []).filter((k) => confirmed.includes(k));
  const fresh = confirmed.filter((k) => !mailed.includes(k));
  const due = confirmed.length > 0 && now - (state.mail_at ?? 0) >= LIMITS.remindHours * 3600e3;
  if (fresh.length || due) {
    const lines = confirmed.map((k) => `- ${current[k]}${fresh.includes(k) ? " (new)" : ""}`);
    const subject = `Work is piling up on the M1Max: ${confirmed.length} problem${confirmed.length > 1 ? "s" : ""}`;
    const body = [`Found ${new Date(now).toISOString()}:`, ...lines, "",
      `Windmill: waiting means queued over ${LIMITS.waitMin} min past its start time; long means running over ${LIMITS.runMin} min.`,
      "Pages and Orca: a Send, a coordinator's mail or a worker's question untouched for 30 min, or a worker Orca marks stuck.",
      `No repeat unless something new appears; a reminder every ${LIMITS.remindHours} h while it lasts; one mail when clear.`,
      "Sent by Windmill f/ops/backlog_watch every 5 min (no AI)."].join("\n");
    return { next: { seen, mailed: confirmed, mail_at: now }, mail: { subject, body } };
  }
  if (!confirmed.length && state.mailed?.length)
    return { next: { seen, mailed: [], mail_at: state.mail_at },
             mail: { subject: "M1Max queues are clear again", body: `Clear at ${new Date(now).toISOString()}.\n\nSent by Windmill f/ops/backlog_watch.` } };
  return { next: { seen, mailed, mail_at: state.mail_at }, mail: null };
}

export async function main(dry_run: boolean = false) {
  const ws = process.env.WM_WORKSPACE;
  const base = (process.env.BASE_INTERNAL_URL || process.env.BASE_URL || "").replace(/\/$/, "") + "/api/";
  const call = async (path: string, body?: unknown) => {
    const r = await fetch(base + path, { method: body === undefined ? "GET" : "POST",
      headers: { Authorization: `Bearer ${process.env.WM_TOKEN}`, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body) });
    if (!r.ok) throw new Error(`${path.split("?")[0]}: HTTP ${r.status}`);
    const text = await r.text();
    try { return JSON.parse(text); } catch { return text; }
  };
  const now = Date.now();
  // shortcut: first 100 queued jobs only; page through if the queue ever holds more than 100.
  const [queue, schedules] = await Promise.all([call(`w/${ws}/jobs/queue/list?per_page=100`),
    call(`w/${ws}/schedules/list?per_page=100`)]);
  const runs = Object.fromEntries(await Promise.all(schedules.filter((s: any) => s.enabled).map(async (s: any) =>
    [s.path, await call(`w/${ws}/jobs/completed/list?schedule_path=${encodeURIComponent(s.path)}&per_page=${LIMITS.failStreak + 2}`)])));
  let host: unknown = null;
  try { host = await call(`w/${ws}/variables/get_value/${HOST}`); } catch { /* missing reads as quiet */ }
  const current = { ...problems(queue, runs, now), ...hostProblems(host, now) };
  let state: State = {};
  let exists = true;
  try { state = JSON.parse(await call(`w/${ws}/variables/get_value/${STATE}`)); } catch { exists = false; }
  const { next, mail } = decide(state, current, now);
  if (dry_run) return { current, mail, next };
  const save = (value: State) => exists ? call(`w/${ws}/variables/update/${STATE}`, { value: JSON.stringify(value) })
    : call(`w/${ws}/variables/create`, { path: STATE, value: JSON.stringify(value), is_secret: false,
        description: "f/ops/backlog_watch: checks each problem has lasted, and what was already mailed" });
  if (mail) {
    try {
      const key = await call(`w/${ws}/variables/get_value/${KEY}`);
      const r = await fetch("https://api.sendgrid.com/v3/mail/send", { method: "POST",
        headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
        body: JSON.stringify({ personalizations: [{ to: [{ email: TO }] }],
          from: { email: "noreply@fastlanedrive.com", name: "Windmill backlog watch" },
          subject: mail.subject, content: [{ type: "text/plain", value: mail.body }], categories: ["backlog-watch"] }) });
      if (!r.ok) throw new Error(`sendgrid HTTP ${r.status}`);
    } catch (e) {
      await save({ ...next, mailed: state.mailed ?? [], mail_at: state.mail_at }); // retry the mail next check
      throw e;
    }
  }
  await save(next);
  return { current, mailed: mail?.subject ?? null };
}
