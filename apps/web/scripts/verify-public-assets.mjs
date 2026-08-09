import { readdir, readFile, stat } from "node:fs/promises";
import { extname, join, relative, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const dist = resolve(root, "dist");
const forbidden = [
  /[A-Za-z]:\\Users\\/i, /\/home\/[A-Za-z0-9._-]+\//, /BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY/,
  /(?:api[_-]?key|token|secret)["'\s:=]+[A-Za-z0-9_-]{16,}/i,
  /google-analytics\.com|segment\.io|mixpanel\.com/i,
];
const imageExtensions = new Set([".png", ".jpg", ".jpeg", ".webp", ".gif", ".tiff"]);

async function walk(directory) {
  const output = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) output.push(...await walk(path)); else output.push(path);
  }
  return output;
}

const files = await walk(dist);
for (const file of files) {
  const name = relative(dist, file);
  const info = await stat(file);
  if (file.endsWith(".map")) throw new Error(`production source map is prohibited: ${name}`);
  if (imageExtensions.has(extname(file).toLowerCase())) throw new Error(`unexpected raster asset; use verified synthetic fixtures only: ${name}`);
  if (info.size > 2 * 1024 * 1024) throw new Error(`oversized public asset: ${name}`);
  const content = await readFile(file, "utf8");
  for (const pattern of forbidden) if (pattern.test(content)) throw new Error(`prohibited public material in ${name}: ${pattern}`);
}
console.log(`public asset verification PASS (${files.length} files)`);
