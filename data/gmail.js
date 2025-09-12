const { google } = require('googleapis');
const Email = require('../models/gmail');
require('dotenv').config({ path: __dirname + '/../.env' });

function getOAuth2Client() {
  return new google.auth.OAuth2(
    process.env.CLIENT_ID,
    process.env.CLIENT_SECRET,
    process.env.REDIRECT_URI
  );
}

function getGmailClient(refreshToken) {
  const oAuth2Client = getOAuth2Client();
  oAuth2Client.setCredentials({ refresh_token: refreshToken || process.env.GMAIL_REFRESH_TOKEN });
  return google.gmail({ version: 'v1', auth: oAuth2Client });
}

function buildQuery(days) {
  const d = Number(days) || Number(process.env.DEFAULT_EMAIL_WINDOW_DAYS) || 30;
  return `newer_than:${d}d`;   // simple query, sab mails aayenge
}

function header(payload, name) {
  const h = payload?.headers?.find(h => h.name.toLowerCase() === name.toLowerCase());
  return h?.value || undefined;
}

function decodeBase64Url(data) {
  if (!data) return '';
  return Buffer.from(data.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8');
}

function extractBodies(payload) {
  let bodyText = '', bodyHtml = '';
  function walk(part) {
    if (!part) return;
    if (part.body?.data && part.mimeType) {
      const decoded = decodeBase64Url(part.body.data);
      if (part.mimeType === 'text/plain') bodyText += decoded;
      if (part.mimeType === 'text/html') bodyHtml += decoded;
    }
    if (Array.isArray(part.parts)) part.parts.forEach(walk);
  }
  walk(payload);
  if (!bodyText && bodyHtml) bodyText = bodyHtml.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  return { bodyText, bodyHtml };
}

async function upsertEmailDoc(userId, msg) {
  const { payload, labelIds = [], id: gmailId, threadId, snippet, internalDate } = msg;
  const subject = header(payload, 'Subject') || '';
  const from = header(payload, 'From') || '';
  const to = header(payload, 'To')?.split(',').map(s => s.trim()) || [];
  const cc = header(payload, 'Cc')?.split(',').map(s => s.trim()) || [];
  const dateHeader = header(payload, 'Date');
  const date = dateHeader ? new Date(dateHeader) : internalDate ? new Date(Number(internalDate)) : new Date();
  const { bodyText, bodyHtml } = extractBodies(payload);

  await Email.updateOne(
    { userId, gmailId },
    { $set: { threadId, subject, from, to, cc, snippet, bodyText, bodyHtml, labels: labelIds, date, fetchedAt: new Date() } },
    { upsert: true }
  );
}

async function listMessageIds(gmail, q) {
  const ids = [];
  let pageToken;
  do {
    const res = await gmail.users.messages.list({ userId: 'me', q, maxResults: 50, pageToken });
    ids.push(...(res.data.messages || []).map(m => m.id));
    pageToken = res.data.nextPageToken;
  } while (pageToken);
  return ids;
}

async function getMessage(gmail, id) {
  const res = await gmail.users.messages.get({ userId: 'me', id, format: 'full' });
  return res.data;
}

async function fetchAndStoreGmail({ userId = "default", days, refreshToken, limit, overrideQuery }) {
  const token = refreshToken || process.env.GMAIL_REFRESH_TOKEN;
  if (!token) throw new Error('GMAIL_REFRESH_TOKEN missing');

  const gmail = getGmailClient(token);
  const q = overrideQuery || buildQuery(days);

  console.log(`[gmail] Fetching with query: ${q}`);

  const ids = await listMessageIds(gmail, q);
  const slice = typeof limit === 'number' ? ids.slice(0, limit) : ids;

  console.log(`[gmail] Found ${slice.length} messages to fetch`);

  let success = 0, failed = 0;
  for (const id of slice) {
    try { 
      await upsertEmailDoc(userId, await getMessage(gmail, id)); 
      success++; 
    }
    catch (e) { 
      failed++; 
      console.error('[gmail] id', id, e?.response?.status || e.message); 
    }
  }
  console.log(`[gmail] Done. Success: ${success}, Failed: ${failed}`);
  return { requested: slice.length, success, failed };
}

function generateAuthUrl() {
  const oAuth2Client = getOAuth2Client();
  return oAuth2Client.generateAuthUrl({
    access_type: 'offline',
    prompt: 'consent',
    scope: ['https://www.googleapis.com/auth/gmail.readonly']
  });
}

async function exchangeCodeForTokens(code) {
  const oAuth2Client = getOAuth2Client();
  const { tokens } = await oAuth2Client.getToken(code);
  return tokens; // includes refresh_token (first consent)
}

module.exports = { fetchAndStoreGmail, generateAuthUrl, exchangeCodeForTokens };
