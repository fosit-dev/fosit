// Copy the Pyodide runtime into public/pyodide and download the exact wheels FOSIT needs,
// verifying each against the SHA-256 in pyodide-lock.json. After this, the app loads
// everything from its own origin: no CDN at runtime, so no third party sees a request.
import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile, access } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "node_modules", "pyodide");
const out = join(here, "..", "public", "pyodide");
const PACKAGES = ["numpy", "scipy", "pandas"];
const RUNTIME = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"];

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");
const exists = (p) => access(p).then(() => true, () => false);

await mkdir(out, { recursive: true });
for (const f of RUNTIME) await copyFile(join(src, f), join(out, f));

const { version } = JSON.parse(await readFile(join(src, "package.json"), "utf8"));
const lock = JSON.parse(await readFile(join(src, "pyodide-lock.json"), "utf8"));
const needed = new Set();
const stack = [...PACKAGES];
while (stack.length) {
  const name = stack.pop();
  if (needed.has(name)) continue;
  needed.add(name);
  stack.push(...lock.packages[name].depends);
}

for (const name of [...needed].sort()) {
  const { file_name, sha256: expected } = lock.packages[name];
  const target = join(out, file_name);
  if ((await exists(target)) && sha256(await readFile(target)) === expected) {
    console.log(`ok     ${file_name}`);
    continue;
  }
  const url = `https://cdn.jsdelivr.net/pyodide/v${version}/full/${file_name}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  const buf = Buffer.from(await res.arrayBuffer());
  if (sha256(buf) !== expected) throw new Error(`${file_name}: SHA-256 mismatch, refusing to use it`);
  await writeFile(target, buf);
  console.log(`fetched ${file_name} (${(buf.length / 1e6).toFixed(1)} MB, sha256 verified)`);
}
console.log(`Pyodide ${version} runtime + ${needed.size} packages in public/pyodide`);
