const fs = require("node:fs");
const path = require("node:path");

const testDirectory = path.join(__dirname, "..", "tests");
const testFiles = fs
    .readdirSync(testDirectory)
    .filter((fileName) => fileName.endsWith(".cjs"))
    .sort();

for (const testFile of testFiles) {
    require(path.join(testDirectory, testFile));
}
