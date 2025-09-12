const DiscordMessage = require('../models/DiscordMessage');


const API = 'https://discord.com/api/v10';

function headers() {
  return {
    'Authorization': `Bot ${process.env.DISCORD_BOT_TOKEN}`,
    'Content-Type': 'application/json'
  };
}

// GET /channels/{channelId}/messages?limit=100&before=messageId
async function fetchPage(channelId, { limit = 100, before } = {}) {
  const url = new URL(`${API}/channels/${channelId}/messages`);
  url.searchParams.set('limit', Math.min(limit, 100));
  if (before) url.searchParams.set('before', before);
  const res = await fetch(url, { headers: headers() });
  if (!res.ok) throw new Error(`Discord API ${res.status}: ${await res.text()}`);
  return res.json();
}

/**
 * opts: { userId, channelId, pages=3, perPage=100 }
 * (pages x perPage) messages max
 */
async function fetchAndStoreDiscord({ userId, channelId, pages = 3, perPage = 100 }) {
  if (!process.env.DISCORD_BOT_TOKEN) throw new Error('DISCORD_BOT_TOKEN missing');
  if (!userId) throw new Error('userId required');
  if (!channelId) throw new Error('channelId required');

  let fetched = 0, success = 0, failed = 0, before;

  for (let p = 0; p < pages; p++) {
    const msgs = await fetchPage(channelId, { limit: perPage, before });
    if (!msgs.length) break;

    for (const m of msgs) {
      fetched++;
      try {
        const doc = {
          userId,
          guildId: m.guild_id || (m.guild_id === undefined ? undefined : m.guild_id),
          channelId,
          messageId: m.id,
          authorId: m.author?.id,
          authorUsername: m.author?.username,
          content: m.content || '',
          attachments: (m.attachments || []).map(a => a.url),
          createdAt: m.timestamp ? new Date(m.timestamp) : new Date(m.id / 4194304 + 1420070400000), // fallback
          fetchedAt: new Date()
        };
        await DiscordMessage.updateOne(
          { userId, channelId, messageId: m.id },
          { $set: doc },
          { upsert: true }
        );
        success++;
      } catch (e) {
        failed++;
        console.error('[discord] upsert failed', channelId, m.id, e.message);
      }
    }

    before = msgs[msgs.length - 1]?.id; // paginate older
  }

  return { requested: fetched, success, failed };
}

module.exports = { fetchAndStoreDiscord };
