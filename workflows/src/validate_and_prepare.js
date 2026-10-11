// n8n Code node "Validate and prepare" (mode: run once for all items).
// Checks the message from the sender, then prepares the CSV log line and, if needed,
// the Teams message. Everything in the payload is data: it is displayed, never acted on.

// ---- Settings (edit here) -------------------------------------------------------
const SETTINGS = {
  // 'dry_run': alerts are saved as files in /files/dry-run-alerts (runtime/dry-run-alerts on your PC).
  // 'live':    alerts are posted to Teams (added in module 3).
  teams_mode: 'dry_run',
};
// ---------------------------------------------------------------------------------

const STATUSES = ['CLEAN', 'PASSED_WITH_WARNINGS', 'PROBLEMS_FOUND', 'NOT_CHECKED'];
const CSV_HEADER = 'received_at,event_id,status,exit_code,tree,errors,warnings,info,top_cause,report_path,alert';

const p = $input.first().json.body || {};

// Same rules as the sender's validate() in delivery_ops_hub/payload.py.
const problems = [];
if (p.schema_version !== 1) problems.push('schema_version must be 1');
if (typeof p.event_id !== 'string' || !p.event_id) problems.push('event_id is missing');
// The event ID becomes part of a file name, so only safe characters are allowed.
else if (!/^[A-Za-z0-9_-]{1,64}$/.test(p.event_id)) problems.push('event_id may only contain letters, digits, - and _');
if (!STATUSES.includes(p.status)) problems.push('status must be one of ' + STATUSES.join(', '));
for (const key of ['sent_at', 'tree']) if (!p[key]) problems.push(key + ' is missing');
if (p.status === 'NOT_CHECKED') {
  if (!p.error_message) problems.push('error_message is required for NOT_CHECKED');
} else if (STATUSES.includes(p.status)) {
  if (!p.counts || typeof p.counts !== 'object') problems.push('counts is missing');
  if (!p.report_path) problems.push('report_path is missing');
}
if (p.top_causes !== undefined && !Array.isArray(p.top_causes)) problems.push('top_causes must be a list');
if (problems.length) return [{ json: { valid: false, problems } }];

const needsAlert = p.status === 'PROBLEMS_FOUND' || p.status === 'NOT_CHECKED';
const counts = p.counts || {};
const causes = Array.isArray(p.top_causes) ? p.top_causes : [];

// One CSV cell. A value starting with = + - @ could run as a formula when the log is
// opened in Excel ("CSV injection"), so it gets a leading apostrophe and stays plain text.
function cell(value) {
  let text = value === null || value === undefined ? '' : String(value);
  if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
  return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}

const receivedAt = DateTime.now().setZone('Europe/London').toISO({ suppressMilliseconds: true });
const csvLine = [receivedAt, p.event_id, p.status, p.exit_code, p.tree, counts.ERROR, counts.WARNING,
  counts.INFO, causes.length ? causes[0].code : '', p.report_path, needsAlert ? SETTINGS.teams_mode : 'none']
  .map(cell).join(',');

// Teams message: an Adaptive Card, in the shape a Teams Workflows webhook accepts.
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

  const body = [
    { type: 'TextBlock', size: 'Large', weight: 'Bolder', color: 'Attention', wrap: true,
      text: notChecked ? 'NOT CHECKED: nothing was verified' : 'PROBLEMS FOUND in a delivery check' },
    { type: 'FactSet', facts },
  ];
  if (causes.length) {
    body.push({ type: 'TextBlock', weight: 'Bolder', wrap: true, text: 'Probable causes (not verdicts)' });
    for (const c of causes.slice(0, 3)) {
      const n = Number(c.file_count) || 0;
      body.push({ type: 'TextBlock', wrap: true,
                  text: `${c.severity}: ${c.summary} (${n} file${n === 1 ? '' : 's'})` });
    }
  }
  teamsMessage = {
    type: 'message',
    attachments: [{
      contentType: 'application/vnd.microsoft.card.adaptive',
      contentUrl: null,
      content: { $schema: 'http://adaptivecards.io/schemas/adaptive-card.json',
                 type: 'AdaptiveCard', version: '1.4', body },
    }],
  };
}

return [{ json: {
  valid: true,
  event_id: p.event_id,
  status: p.status,
  needs_alert: needsAlert,
  alert_mode: needsAlert ? SETTINGS.teams_mode : 'none',
  csv_header: CSV_HEADER,
  csv_line: csvLine,
  teams_message: teamsMessage,
} }];
