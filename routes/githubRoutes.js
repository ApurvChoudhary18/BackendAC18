const express = require('express');
const router = express.Router();
const { fetchAndStoreCommits, listUserRepos } = require('../data/github');

router.get('/repos', async (_req, res) => {
  try {
    const repos = await listUserRepos();
    const minimal = repos.map(r => ({
      full_name: r.full_name,
      private: r.private,
      default_branch: r.default_branch,
      pushed_at: r.pushed_at,
    }));
    res.json({ ok: true, count: minimal.length, repos: minimal });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

router.get('/fetch', async (req, res) => {
  try {
    const userId = req.query.userId || 'demo';
    const owner = req.query.owner;
    const repo  = req.query.repo;
    const sinceDays = req.query.days ? Number(req.query.days) : 30;
    const limit = req.query.limit ? Number(req.query.limit) : 50;
    const includeFiles = req.query.includeFiles === 'true';

    const result = await fetchAndStoreCommits({ userId, owner, repo, sinceDays, limit, includeFiles });
    res.json({ ok: true, owner, repo, ...result });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

module.exports = router; // 👈 IMPORTANT
