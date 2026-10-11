// n8n Code node "Make log line" (mode: run once for all items).
// Runs after "Read existing log". If no log file exists yet, it starts one with the
// Excel marker (UTF-8 byte order mark) and a header row. The line is then appended.

const prep = $('Validate and prepare').first().json;
const previous = $input.first();
const logExists = Boolean(previous.binary && Object.keys(previous.binary).length);

const text = (logExists ? '' : '﻿' + prep.csv_header + '\r\n') + prep.csv_line + '\r\n';

return [{
  json: {},
  binary: {
    data: {
      data: Buffer.from(text, 'utf8').toString('base64'),
      mimeType: 'text/csv',
      fileName: 'delivery-checks.csv',
    },
  },
}];
