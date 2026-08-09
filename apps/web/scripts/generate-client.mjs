import { execFileSync } from "node:child_process";
import { readFile, rename, rm } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const outputPath = resolve(root, "src/api/generated.ts");
const temporaryPath = `${outputPath}.tmp`;
const cliPath = resolve(root, "node_modules/openapi-typescript/bin/cli.js");
execFileSync(process.execPath, [cliPath, "openapi.json", "--alphabetize", "--immutable", "--output", "src/api/generated.ts.tmp"], {
  cwd: root,
  stdio: "ignore",
});
const generated = await readFile(temporaryPath, "utf8");
if (process.argv.includes("--check")) {
  const current = await readFile(outputPath, "utf8");
  await rm(temporaryPath, { force: true });
  if (current !== generated) {
    throw new Error("generated client is stale; run npm run api:generate");
  }
} else {
  try {
    await rename(temporaryPath, outputPath);
  } finally {
    await rm(temporaryPath, { force: true });
  }
}
