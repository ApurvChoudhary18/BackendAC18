const express = require('express');
const router = express.Router();
const { fetchAndStoreGmail, generateAuthUrl, exchangeCodeForTokens } = require('../data/gmail');

router.get('/auth-url', (_req, res) => res.json({ ok: true, url: generateAuthUrl() }));

router.get('/oauth2callback', async (req, res) => {
  try {
    const { code } = req.query;
    if (!code) return res.status(400).send('Missing code');
    const tokens = await exchangeCodeForTokens(code);
    res.send(`<pre>Save refresh_token to .env GMAIL_REFRESH_TOKEN:\n\n${JSON.stringify(tokens, null, 2)}</pre>`);
  } catch (e) { res.status(500).send('OAuth error: ' + e.message); }
});

router.get("/debug-secret", (_req, res) => {
    const s = process.env.CLIENT_SECRET || "";
    res.json({
      hasSecret: !!s,
      length: s.length,
      redirectUri: process.env.REDIRECT_URI
    });
  });

  // GET /api/emails/fetch-sent?userId=demo&days=180&limit=200
router.get('/fetch-sent', async (req, res) => {
    try {
      const userId = req.query.userId || 'demo';
      const days = req.query.days ? Number(req.query.days) : 180;
      const limit = req.query.limit ? Number(req.query.limit) : 200;
      const q = `newer_than:${days}d in:sent`; // only SENT mailbox
      const result = await fetchAndStoreGmail({ userId, days, limit, overrideQuery: q });
      res.json({ ok: true, box: 'SENT', ...result });
    } catch (e) {
      res.status(500).json({ ok: false, error: e.message });
    }
  });
  

  router.get("/debug-refresh", (_req, res) => {
    const token = process.env.GMAIL_REFRESH_TOKEN || "";
    res.json({
      hasRefresh: !!token,
      length: token.length
    });
  });

router.get('/debug-env', (_req, res) => {
    res.json({
      port: process.env.PORT,
      clientId: process.env.CLIENT_ID,
      clientIdEndsWith: process.env.CLIENT_ID?.slice(-23),
      redirectUri: process.env.REDIRECT_URI
    });
  });
  

// GET /api/emails/fetch?userId=demo&days=30&limit=50
router.get('/fetch', async (req, res) => {
  try {
    const userId = req.query.userId || 'demo';
    const days = req.query.days ? Number(req.query.days) : undefined;
    const limit = req.query.limit ? Number(req.query.limit) : undefined;
    const result = await fetchAndStoreGmail({ userId, days, limit });
    res.json({ ok: true, ...result });
  } catch (e) { res.status(500).json({ ok: false, error: e.message }); }
});

module.exports = router;
