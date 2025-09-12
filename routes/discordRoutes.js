// backend/routes/discordRoutes.js
const express = require('express');
const router = express.Router();
const { fetchAndStoreDiscord } = require('../data/discord');

// ✅ route file load hone par log
console.log('[discordRoutes] loaded');

// simple ping to verify mount
router.get('/ping', (_req, res) => {
  res.json({ ok: true, where: 'discordRoutes' });
});

// token visible?
router.get('/debug-token', (_req, res) => {
  const t = process.env.DISCORD_BOT_TOKEN || '';
  res.json({ hasToken: !!t, length: t.length });
});

// token valid with Discord?
router.get('/whoami', async (_req, res) => {
  try {
    const t = process.env.DISCORD_BOT_TOKEN || '';
    if (!t) return res.status(400).json({ ok:false, error:'DISCORD_BOT_TOKEN missing' });

    const r = await fetch('https://discord.com/api/v10/users/@me', {
      headers: { Authorization: `Bot ${t}` }
    });
    const text = await r.text();
    let body; try { body = JSON.parse(text); } catch { body = text; }
    res.status(r.ok ? 200 : 500).json({ ok: r.ok, status: r.status, body });
  } catch (e) {
    res.status(500).json({ ok:false, error:e.message });
  }
});

// fetch messages
// GET /api/discord/fetch?userId=demo&channelId=123...&pages=2&perPage=50
router.get('/fetch', async (req, res) => {
  try {
    const userId   = req.query.userId || 'demo';
    const channelId= req.query.channelId;
    const pages    = req.query.pages ? Number(req.query.pages) : 2;
    const perPage  = req.query.perPage ? Number(req.query.perPage) : 50;

    const result = await fetchAndStoreDiscord({ userId, channelId, pages, perPage });
    res.json({ ok: true, channelId, ...result });
  } catch (e) {
    res.status(500).json({ ok:false, error:e.message });
  }
});

module.exports = router; // ✅ IMPORTANT
