const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const ROOT = path.join(__dirname, "..");
const SRC_DIR = path.join(ROOT, "src");

function readAllSourceFiles() {
  return fs
    .readdirSync(SRC_DIR)
    .filter((f) => f.endsWith(".ts"))
    .map((f) => fs.readFileSync(path.join(SRC_DIR, f), "utf8"))
    .join("\n");
}

test("typescript compiles with no errors (tsc --noEmit)", () => {
  execFileSync("tsc", ["--noEmit", "-p", path.join(ROOT, "tsconfig.json")], { stdio: "pipe" });
});

test("extension source never imports a blockchain SDK", () => {
  const source = readAllSourceFiles();
  const forbidden = ["@solana/web3.js", "\"ethers\"", "'ethers'", "@project-serum", "web3.js"];
  for (const name of forbidden) {
    assert.ok(!source.includes(name), `extension source must never import ${name}`);
  }
});

test("extension source never references private key, seed phrase, or mnemonic storage", () => {
  const source = readAllSourceFiles().toLowerCase();
  const forbidden = [
    "privatekey",
    "private_key",
    "seedphrase",
    "seed_phrase",
    "mnemonic",
    "secretkey",
    "secret_key",
  ];
  for (const term of forbidden) {
    assert.ok(!source.includes(term), `extension source must never reference ${term}`);
  }
});

test("apiClient.ts is the only file that calls fetch()", () => {
  const files = fs.readdirSync(SRC_DIR).filter((f) => f.endsWith(".ts") && f !== "apiClient.ts");
  for (const file of files) {
    const content = fs.readFileSync(path.join(SRC_DIR, file), "utf8");
    assert.ok(!content.includes("fetch("), `${file} must not call fetch() directly — go through apiClient.ts`);
  }
});

test("manifest.json requests permissions no broader than the Local API host", () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "manifest.json"), "utf8"));
  const hostPermissions = manifest.host_permissions || [];

  assert.ok(hostPermissions.length > 0, "expected explicit host_permissions");
  assert.ok(!hostPermissions.includes("<all_urls>"), "must never request access to all URLs");

  for (const pattern of hostPermissions) {
    const isLocalApiOnly = pattern.startsWith("http://127.0.0.1:8765") || pattern.startsWith("http://localhost:8765");
    assert.ok(isLocalApiOnly, `host permission ${pattern} is broader than the Local API origin`);
  }

  assert.deepEqual(manifest.permissions, ["storage"], "expected exactly the storage permission, nothing more");
});

test("manifest declares manifest_version 3", () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "manifest.json"), "utf8"));
  assert.equal(manifest.manifest_version, 3);
});
