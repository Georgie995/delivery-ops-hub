// n8n Code node "Make dry-run alert file" (mode: run once for all items).
// Dry-run mode: the Teams message is saved exactly as it would be posted.

const prep = $('Validate and prepare').first().json;
const text = JSON.stringify(prep.teams_message, null, 2);
const fileName = `teams-${prep.event_id}.json`;  // event_id was checked to be safe characters only

return [{
  json: { path: `/files/dry-run-alerts/${fileName}` },
  binary: {
    data: {
      data: Buffer.from(text, 'utf8').toString('base64'),
      mimeType: 'application/json',
      fileName,
    },
  },
}];
