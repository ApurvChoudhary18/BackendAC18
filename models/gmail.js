// backend/models/gmail.js
const mongoose = require('mongoose');

const EmailSchema = new mongoose.Schema(
  {
    userId: { type: String, index: true, required: true },
    gmailId: { type: String, required: true, index: true },
    threadId: { type: String, index: true },
    subject: String,
    from: String,
    to: [String],
    cc: [String],
    snippet: String,
    bodyText: String,
    bodyHtml: String,
    labels: [String],
    date: Date,
    fetchedAt: { type: Date, default: Date.now }
  },
  { timestamps: true }
);

// Avoid duplicates per user/message
EmailSchema.index({ userId: 1, gmailId: 1 }, { unique: true });

module.exports = mongoose.model('Email', EmailSchema);
