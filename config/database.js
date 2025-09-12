const mongoose = require("mongoose")
require("dotenv").config();

exports.dbConnect = () => {
    mongoose.connect(process.env.MONGODB_URL)
    .then(() => console.log("DB connected Successfully"))
    .catch((error) => {
        console.log(error);
        console.log("DB connection Failed");
        process.exit(1)
    })
}