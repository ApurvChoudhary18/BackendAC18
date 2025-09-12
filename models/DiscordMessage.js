const mongoose = require('mongoose');

const DiscordMessageSchema = new mongoose.Schema({
  userId: { type: String, index: true, required: true },
  guildId: String,
  channelId: { type: String, index: true },
  messageId: { type: String, index: true },
  authorId: String,
  authorUsername: String,
  content: String,
  attachments: [String],
  createdAt: Date,
  fetchedAt: { type: Date, default: Date.now },
}, { timestamps: true });

DiscordMessageSchema.index({ userId: 1, channelId: 1, messageId: 1 }, { unique: true });

module.exports = mongoose.model('DiscordMessage', DiscordMessageSchema);
