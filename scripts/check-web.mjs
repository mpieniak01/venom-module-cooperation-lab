import { readFileSync, writeFileSync, mkdirSync, existsSync, symlinkSync, unlinkSync, readdirSync } from "node:fs";
import { resolve, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";
const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const host = resolve(process.argv[2] ?? "../..");
const results = join(root, "test-results");
mkdirSync(results, { recursive: true });
const config = JSON.parse(readFileSync(join(root, "web-next/tsconfig.json"), "utf8"));
config.extends = join(host, "web-next/tsconfig.json");
config.include = [join(root, "web-next/**/*.ts"), join(root, "web-next/**/*.tsx"), join(root, "tests/web/*.ts"), join(root, "tests/web/*.tsx")];
config.exclude = [join(root, "node_modules")];
const tsconfig = join(results, "web-tsconfig.json");
writeFileSync(tsconfig, JSON.stringify(config));
const eslint = join(results, "web-eslint.config.mjs");
writeFileSync(eslint, `import config from ${JSON.stringify(pathToFileURL(join(host, "web-next/eslint.config.mjs")).href)}; export default [...config, { rules: { "@next/next/no-html-link-for-pages": "off" } }];\n`);
const modules = join(root, "node_modules");
let linked = false;
if (!existsSync(modules)) { symlinkSync(join(host, "web-next/node_modules"), modules, "dir"); linked = true; }
function run(executable, args, extra = {}) {
  const result = spawnSync(executable, args, { cwd: root, stdio: "inherit", env: { ...process.env, ...extra } });
  if (result.error || result.status !== 0) throw result.error ?? new Error("Web check failed: " + executable);
}
try {
  run(join(host, "web-next/node_modules/.bin/tsc"), ["--project", tsconfig, "--noEmit"]);
  run(join(host, "web-next/node_modules/.bin/eslint"), ["web-next", "tests/web", "--max-warnings", "0", "--config", eslint]);
  const tests = readdirSync(join(root, "tests/web")).filter((name) => /\.test\.tsx?$/.test(name)).map((name) => join(root, "tests/web", name));
  run(process.execPath, ["--import", join(host, "web-next/node_modules/tsx/dist/loader.mjs"),
    "--import", join(root, "tests/web/setup.ts"),
    "--experimental-test-coverage", "--test-coverage-include=web-next/**",
    "--test-reporter=spec", "--test-reporter-destination=stdout",
    "--test-reporter=lcov", "--test-reporter-destination=test-results/lcov.info", "--test", ...tests],
    { TSX_TSCONFIG_PATH: tsconfig });
} finally {
  if (linked) unlinkSync(modules);
}
