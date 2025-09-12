// backend/models/Commit.js
const mongoose = require('mongoose');

const CommitSchema = new mongoose.Schema(
  {
    userId: { type: String, index: true, required: true },
    owner:  { type: String, index: true, required: true },
    repo:   { type: String, index: true, required: true },

    // primary id for a commit
    sha:    { type: String, index: true, required: true },

    // (optional) backward-compat if you had commitId earlier; DO NOT make this unique
    commitId: { type: String },

    commitMessage: String,
    authorName: String,
    authorEmail: String,
    authorDate: Date,
    committerName: String,
    committerEmail: String,
    committerDate: Date,

    htmlUrl: String,
    filesChanged: [String],
    additions: Number,
    deletions: Number,

    fetchedAt: { type: Date, default: Date.now }
  },
  { timestamps: true }
);

// unique per user + repo + sha
CommitSchema.index({ userId: 1, owner: 1, repo: 1, sha: 1 }, { unique: true });

module.exports = mongoose.model('Commit', CommitSchema);
