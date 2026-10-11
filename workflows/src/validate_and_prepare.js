// n8n Code node "Validate and prepare" (mode: run once for all items).
// Checks the message, then prepares the CSV log line and, if needed, the Teams message.
// Two kinds of message arrive: delivery checks (from the delivery-ops-hub sender) and
// job events (from job-watch, kind "job_event"). Each has its own log file.
// Everything in the payload is data: it is displayed, never acted on.

// ---- Settings (edit here) -------------------------------------------------------
const SETTINGS = {
  // Only 'dry_run' is implemented: alerts are saved as files in /files/dry-run-alerts
  // (runtime/dry-run-alerts on your PC). Posting to real Teams needs a work or school
  // Microsoft 365 account with the Workflows app; personal Teams doesn't have it
  // (checked 2026-10-11, see docs/DECISIONS.md).
  teams_mode: 'dry_run',
};
// ---------------------------------------------------------------------------------

const p = $input.first().json.body || {};

// One CSV cell. A value starting with = + - @ could run as a formula when the log is
// opened in Excel ("CSV injection"), so it gets a leading apostrophe and stays plain text.
function cell(value) {
  let text = value === null || value === undefined ? '' : String(value);
  if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
  return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}

function commonProblems() {
  const problems = [];
  if (p.schema_version !== 1) problems.push('schema_version must be 1');
  if (typeof p.event_id !== 'string' || !p.event_id) problems.push('event_id is missing');
  // The event ID becomes part of a file name, so only safe characters are allowed.
  else if (!/^[A-Za-z0-9_-]{1,64}$/.test(p.event_id)) problems.push('event_id may only contain letters, digits, - and _');
  return problems;
}

function card(color, title, facts, extraBlocks = []) {
  // An Adaptive Card, in the shape a Teams Workflows webhook accepts.
  return {
    type: 'message',
    attachments: [{
      contentType: 'application/vnd.microsoft.card.adaptive',
      contentUrl: null,
      content: { $schema: 'http://adaptivecards.io/schemas/adaptive-card.json', type: 'AdaptiveCard', version: '1.4',
                 body: [{ type: 'TextBlock', size: 'Large', weight: 'Bolder', color, wrap: true, text: title },
                        ...extraBlocks, { type: 'FactSet', facts }] },
    }],
  };
}

const receivedAt = DateTime.now().setZone('Europe/London').toISO({ suppressMilliseconds: true });
const result = p.kind === 'job_event' ? jobEvent() : deliveryCheck();
return [{ json: result }];


// --- Delivery checks (from the delivery-ops-hub sender) ------------------------------------

function deliveryCheck() {
  const STATUSES = ['CLEAN', 'PASSED_WITH_WARNINGS', 'PROBLEMS_FOUND', 'NOT_CHECKED'];
  // Same rules as the sender's validate() in delivery_ops_hub/payload.py.
  const problems = commonProblems();
  if (!STATUSES.includes(p.status)) problems.push('status must be one of ' + STATUSES.join(', '));
  for (const key of ['sent_at', 'tree']) if (!p[key]) problems.push(key + ' is missing');
  if (p.status === 'NOT_CHECKED') {
    if (!p.error_message) problems.push('error_message is required for NOT_CHECKED');
  } else if (STATUSES.includes(p.status)) {
    if (!p.counts || typeof p.counts !== 'object') problems.push('counts is missing');
    if (!p.report_path) problems.push('report_path is missing');
  }
  if (p.top_causes !== undefined && !Array.isArray(p.top_causes)) problems.push('top_causes must be a list');
  if (problems.length) return { valid: false, problems };

  const needsAlert = p.status === 'PROBLEMS_FOUND' || p.status === 'NOT_CHECKED';
  const counts = p.counts || {};
  const causes = Array.isArray(p.top_causes) ? p.top_causes : [];
  const csvLine = [receivedAt, p.event_id, p.status, p.exit_code, p.tree, counts.ERROR, counts.WARNING,
    counts.INFO, causes.length ? causes[0].code : '', p.report_path, needsAlert ? SETTINGS.teams_mode : 'none']
    .map(cell).join(',');

  let teamsMessage = null;
  if (needsAlert) {
    const notChecked = p.status === 'NOT_CHECKED';
    const facts = [{ title: 'Folder', value: String(p.tree) }];
    if (notChecked) {
      facts.push({ title: 'Reason', value: String(p.error_message) });
    } else {
      facts.push({ title: 'Errors / warnings / info',
                   value: `${counts.ERROR ?? 0} / ${counts.WARNING ?? 0} / ${counts.INFO ?? 0}` });
      facts.push({ title: 'Full report', value: String(p.report_path) });
    }
    facts.push({ title: 'Checked at', value: String(p.sent_at) }, { title: 'Event ID', value: p.event_id });
    const extra = [];
    if (causes.length) {
      extra.push({ type: 'TextBlock', weight: 'Bolder', wrap: true, text: 'Probable causes (not verdicts)' });
      for (const c of causes.slice(0, 3)) {
        const n = Number(c.file_count) || 0;
        extra.push({ type: 'TextBlock', wrap: true, text: `${c.severity}: ${c.summary} (${n} file${n === 1 ? '' : 's'})` });
      }
    }
    // Facts first, then causes, as before.
    const message = card('Attention', notChecked ? 'NOT CHECKED: nothing was verified' : 'PROBLEMS FOUND in a delivery check', facts);
    message.attachments[0].content.body.push(...extra);
    teamsMessage = message;
  }
  return { valid: true, event_id: p.event_id, status: p.status, needs_alert: needsAlert,
           alert_mode: needsAlert ? SETTINGS.teams_mode : 'none', log_path: '/files/logs/delivery-checks.csv',
           csv_header: 'received_at,event_id,status,exit_code,tree,errors,warnings,info,top_cause,report_path,alert',
           csv_line: csvLine, teams_message: teamsMessage };
}


// --- Job events (from job-watch) ---------------------------------------------------------

function jobEvent() {
  const EVENTS = ['started', 'finished', 'failed', 'stalled', 'resumed', 'interrupted'];
  const problems = commonProblems();
  if (!EVENTS.includes(p.event)) problems.push('event must be one of ' + EVENTS.join(', '));
  if (typeof p.job_name !== 'string' || !p.job_name.trim()) problems.push('job_name is missing');
  if (typeof p.program !== 'string') problems.push('program is missing');
  if (typeof p.elapsed_seconds !== 'number') problems.push('elapsed_seconds must be a number');
  if (!p.progress || typeof p.progress !== 'object') problems.push('progress is missing');
  if (problems.length) return { valid: false, problems };

  const needsAlert = p.event !== 'started';      // "started" is logged only
  const g = p.progress;
  const csvLine = [receivedAt, p.event_id, p.job_name, p.program, p.event, p.elapsed_seconds, g.bytes, g.files,
    g.current_file, p.exit_code, p.stalled_for_seconds, needsAlert ? SETTINGS.teams_mode : 'none']
    .map(cell).join(',');

  let teamsMessage = null;
  if (needsAlert) {
    const hms = s => { s = Math.round(Number(s) || 0);
      return `${Math.floor(s / 3600)}:${String(Math.floor(s % 3600 / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; };
    const size = n => { if (n === null || n === undefined) return 'unknown'; let v = Number(n);
      for (const u of ['B', 'KB', 'MB', 'GB', 'TB']) { if (v < 1000 || u === 'TB') return u === 'B' ? `${v} B` : `${v.toFixed(1)} ${u}`; v /= 1000; } };
    const name = String(p.job_name);
    const lines = {
      finished: ['Good', `FINISHED: ${name}`, `The job finished successfully after ${hms(p.elapsed_seconds)}.`],
      failed: ['Attention', `FAILED: ${name}`, `The job ended with exit code ${p.exit_code}.`],
      stalled: ['Warning', `STALLED: ${name}`, `No progress for ${hms(p.last_progress_seconds_ago)}. The job is still running; nothing has been stopped.`],
      resumed: ['Good', `RESUMED: ${name}`, `Progress again after being stalled for ${hms(p.stalled_for_seconds)}.`],
      interrupted: ['Warning', `INTERRUPTED: ${name}`, 'Watcher stopped (Ctrl-C): job outcome unknown. Check the job directly.'],
    }[p.event];
    const facts = [
      { title: 'Program', value: String(p.program) },
      { title: 'Running for', value: hms(p.elapsed_seconds) },
      { title: 'Done so far', value: `${g.files ?? 'unknown'} files, ${size(g.bytes)}` },
    ];
    if (g.current_file) facts.push({ title: p.event === 'stalled' ? 'Last file' : 'File', value: String(g.current_file) });
    if (p.event === 'failed' && p.error_tail) facts.push({ title: 'Last error output', value: String(p.error_tail) });
    facts.push({ title: 'Sent at', value: String(p.sent_at) }, { title: 'Event ID', value: p.event_id });
    teamsMessage = card(lines[0], lines[1], facts, [{ type: 'TextBlock', wrap: true, text: lines[2] }]);
  }
  return { valid: true, event_id: p.event_id, status: p.event, needs_alert: needsAlert,
           alert_mode: needsAlert ? SETTINGS.teams_mode : 'none', log_path: '/files/logs/job-events.csv',
           csv_header: 'received_at,event_id,job_name,program,event,elapsed_seconds,bytes,files,current_file,exit_code,stalled_for_seconds,alert',
           csv_line: csvLine, teams_message: teamsMessage };
}
