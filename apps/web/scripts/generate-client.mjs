import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFile, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const outputPath = resolve(root, "src/api/generated.ts");
const temporaryPath = `${outputPath}.tmp`;
const cliPath = resolve(root, "node_modules/openapi-typescript/bin/cli.js");
const schemaPath = resolve(root, "openapi.json");
execFileSync(process.execPath, [cliPath, "openapi.json", "--alphabetize", "--immutable", "--output", "src/api/generated.ts.tmp"], {
  cwd: root,
  stdio: "ignore",
});
const canonicalSchema = (await readFile(schemaPath, "utf8")).replaceAll("\r\n", "\n");
const schemaHash = createHash("sha256").update(canonicalSchema).digest("hex");
const generated = `// openapi-source-sha256: ${schemaHash}\n${await readFile(temporaryPath, "utf8")}`;
if (process.argv.includes("--check")) {
  const current = await readFile(outputPath, "utf8");
  await rm(temporaryPath, { force: true });
  if (current.replaceAll("\r\n", "\n") !== generated.replaceAll("\r\n", "\n")) {
    throw new Error("generated client is stale; run npm run api:generate");
  }
} else {
  try {
    await rm(temporaryPath, { force: true });
    await writeFile(outputPath, generated);
  } finally {
    await rm(temporaryPath, { force: true });
  }
}
