const express = require("express");
const app = express();

const dotenv = require("dotenv");
dotenv.config(); // ✅ env pehle load

const PORT = process.env.PORT || 5000;

const database = require("./config/database");
database.dbConnect();

// ✅ mount routes
const emailRoutes   = require("./routes/emailRoutes");
const githubRoutes  = require("./routes/githubRoutes");
const discordRoutes = require("./routes/discordRoutes"); // <-- yeh zaroor add ho

app.use("/api/emails", emailRoutes);
app.use("/api/github", githubRoutes);
app.use("/api/discord", discordRoutes); // <-- aur yeh

app.listen(PORT, () => {
  console.log(`App is listening on PORT no. ${PORT}`);
  console.log('[index] mounted /api/discord'); // ✅ mount confirmation
});
