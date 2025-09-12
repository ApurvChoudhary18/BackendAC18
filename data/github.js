// backend/data/github.js
const Commit = require('../models/Commit');

function ghHeaders(token) {
  return {
    'Accept': 'application/vnd.github+json',
    'Authorization': `Bearer ${token}`,
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'ShadowShift/1.0'
  };
}

function isoSince(days = 30) {
  const d = new Date();
  d.setDate(d.getDate() - Number(days || 30));
  return d.toISOString();
}

async function listCommits({ owner, repo, since, perPage = 50, page = 1, token }) {
  const url = new URL(`https://api.github.com/repos/${owner}/${repo}/commits`);
  url.searchParams.set('since', since);
  url.searchParams.set('per_page', Math.min(perPage, 100));
  url.searchParams.set('page', page);
  const res = await fetch(url, { headers: ghHeaders(token) });
  if (!res.ok) throw new Error(`list commits ${res.status}: ${await res.text()}`);
  return res.json();
}

async function getCommit({ owner, repo, sha, token }) {
  const url = `https://api.github.com/repos/${owner}/${repo}/commits/${sha}`;
  const res = await fetch(url, { headers: ghHeaders(token) });
  if (!res.ok) throw new Error(`commit detail ${res.status}: ${await res.text()}`);
  return res.json();
}

async function fetchAndStoreCommits({
  userId, owner, repo, sinceDays = 30, limit = 100, includeFiles = false, token = process.env.GITHUB_TOKEN
}) {
  if (!userId) throw new Error('userId required');
  if (!owner || !repo) throw new Error('owner and repo required');
  if (!token) throw new Error('GITHUB_TOKEN missing');

  const since = isoSince(sinceDays);
  let page = 1, fetched = 0, success = 0, failed = 0;

  while (fetched < limit) {
    const toGet = Math.min(100, limit - fetched);
    const commits = await listCommits({ owner, repo, since, perPage: toGet, page, token });
    if (!commits.length) break;

    for (const c of commits) {
      if (fetched >= limit) break;
      fetched++;

      try {
        let filesChanged = [], additions = 0, deletions = 0;
        if (includeFiles) {
          const detail = await getCommit({ owner, repo, sha: c.sha, token });
          if (Array.isArray(detail.files)) {
            filesChanged = detail.files.map(f => f.filename);
            additions = detail.stats?.additions || 0;
            deletions = detail.stats?.deletions || 0;
          }
        }

        const doc = {
          userId, owner, repo, sha: c.sha,
          commitMessage: c.commit?.message || '',
          authorName: c.commit?.author?.name || c.author?.login || '',
          authorEmail: c.commit?.author?.email || '',
          authorDate: c.commit?.author?.date ? new Date(c.commit.author.date) : undefined,
          committerName: c.commit?.committer?.name || c.committer?.login || '',
          committerEmail: c.commit?.committer?.email || '',
          committerDate: c.commit?.committer?.date ? new Date(c.commit.committer.date) : undefined,
          htmlUrl: c.html_url,
          filesChanged, additions, deletions,
          fetchedAt: new Date()
        };

        await Commit.updateOne(
          { userId, owner, repo, sha: c.sha },
          { $set: doc },
          { upsert: true }
        );
        success++;
      } catch (e) {
        failed++;
        console.error('[github] upsert failed', owner, repo, c.sha, e.message);
      }
    }
    page++;
  }

  return { requested: fetched, success, failed };
}

async function listUserRepos({ token = process.env.GITHUB_TOKEN, visibility = 'all' } = {}) {
  const url = new URL('https://api.github.com/user/repos');
  url.searchParams.set('per_page', '100');
  url.searchParams.set('visibility', visibility);
  const res = await fetch(url, { headers: ghHeaders(token) });
  if (!res.ok) throw new Error(`list repos ${res.status}: ${await res.text()}`);
  return res.json();
}

module.exports = { fetchAndStoreCommits, listUserRepos };
