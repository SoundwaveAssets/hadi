// Applique une table de traduction aux sources.
// Usage : node scripts/i18n-apply.mjs <map.json> [--dry]
import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { parse } from "@babel/parser";
import traverseModule from "@babel/traverse";

const traverse = traverseModule.default ?? traverseModule;
const ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const SCAN = ["app", "components"];
const DRY = process.argv.includes("--dry");
const MAP = JSON.parse(readFileSync(process.argv[2], "utf8"));

const TEXT_PROPS = new Set(["label", "title", "placeholder", "description", "hint", "aria-label", "emptyMessage", "subtitle", "note", "alt"]);
const SKIP_PROPS = new Set(["className", "href", "key", "src", "type", "name", "value", "id", "role", "rel", "target", "htmlFor", "autoComplete", "step", "min", "max", "pattern", "variant", "size", "tone", "align", "width"]);
const MSG_CALLS = new Set(["setError", "setSuccess", "setInfo", "setMessage", "extractError"]);

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (full.endsWith(".tsx")) yield full;
  }
}

const norm = (s) => s.replace(/\s+/g, " ").trim();

function insideSkip(path) {
  let p = path;
  while (p) {
    if (p.isCallExpression() && p.node.callee.type === "Identifier" && (p.node.callee.name === "t" || p.node.callee.name === "cn")) return true;
    if (p.isJSXAttribute() && SKIP_PROPS.has(p.node.name.name)) return true;
    p = p.parentPath;
  }
  return false;
}

function enclosingFunction(path) {
  // le composant : la fonction la plus externe, pas la callback de .map()
  let fn = path.getFunctionParent();
  if (!fn) return null;
  let outer = fn;
  while ((fn = fn.getFunctionParent())) outer = fn;
  const body = outer.node.body;
  if (body.type !== "BlockStatement") return null;
  return { bodyStart: body.start + 1, key: body.start };
}

const newKeys = new Map(); // key -> {fr, en}
const manual = [];
let filesTouched = 0;
let replaced = 0;

for (const base of SCAN) {
  for (const file of walk(join(ROOT, base))) {
    const rel = relative(ROOT, file).replaceAll("\\", "/");
    if (rel.includes("/lib/")) continue;
    const src = readFileSync(file, "utf8");
    let ast;
    try {
      ast = parse(src, { sourceType: "module", plugins: ["typescript", "jsx"] });
    } catch {
      continue;
    }

    const edits = []; // {start, end, text}
    const fnInjections = new Map(); // bodyStart -> true
    let usesT = src.includes('from "@/lib/i18n"');

    const use = (node, path, kind, raw, wrap) => {
      const text = norm(raw);
      const entry = MAP[text];
      if (!entry) return;
      const [key, fr, en] = entry;
      if (fr === "") {
        manual.push(`${rel}:${node.loc.start.line} [remove] ${text}`);
        return;
      }
      const fn = enclosingFunction(path);
      if (!fn) {
        manual.push(`${rel}:${node.loc.start.line} [module-scope] ${text}`);
        return;
      }
      if (fr !== null || en !== null) newKeys.set(key, { fr: fr ?? text, en: en ?? text });
      edits.push({ start: node.start, end: node.end, text: wrap(key) });
      fnInjections.set(fn.bodyStart, true);
      usesT = true;
      replaced++;
    };

    traverse(ast, {
      JSXText(path) {
        if (insideSkip(path)) return;
        const raw = path.node.value;
        const text = norm(raw);
        if (!MAP[text]) return;
        // remplace uniquement la partie non blanche pour garder l'indentation
        const lead = raw.length - raw.trimStart().length;
        const trail = raw.length - raw.trimEnd().length;
        const fakeNode = { start: path.node.start + lead, end: path.node.end - trail, loc: path.node.loc };
        use(fakeNode, path, "text", raw, (k) => `{t("${k}")}`);
      },
      JSXAttribute(path) {
        const name = path.node.name.name;
        if (SKIP_PROPS.has(name)) return;
        const v = path.node.value;
        if (!v) return;
        if (v.type === "StringLiteral" && (TEXT_PROPS.has(name) || MAP[norm(v.value)])) {
          use(v, path, `prop:${name}`, v.value, (k) => `{t("${k}")}`);
        } else if (v.type === "JSXExpressionContainer" && v.expression.type === "StringLiteral" && !insideSkip(path)) {
          use(v.expression, path, `prop:${name}`, v.expression.value, (k) => `t("${k}")`);
        }
      },
      StringLiteral(path) {
        if (insideSkip(path)) return;
        const parent = path.parentPath;
        if (parent.isJSXAttribute() || parent.isJSXExpressionContainer()) return; // déjà traité
        if (parent.isImportDeclaration() || parent.isExportDeclaration()) return;
        const inJsx = parent.findParent((p) => p.isJSXElement() || p.isJSXFragment());
        const isMsg = parent.isCallExpression() && parent.node.callee.type === "Identifier" && MSG_CALLS.has(parent.node.callee.name);
        const isCond = (parent.isConditionalExpression() || parent.isLogicalExpression()) && inJsx;
        const isObjLabel = parent.isObjectProperty() && ["label", "title", "description", "hint"].includes(parent.node.key.name ?? parent.node.key.value);
        if (!(isMsg || isCond || isObjLabel)) return;
        use(path.node, path, "expr", path.node.value, (k) => `t("${k}")`);
      },
    });

    if (edits.length === 0) continue;

    let out = src;
    // injections de `const t = useT();` puis remplacements, du plus loin au plus proche
    const all = [
      ...edits,
      ...[...fnInjections.keys()].map((pos) => ({ start: pos, end: pos, text: "\n  const t = useT();" })),
    ].sort((a, b) => b.start - a.start || b.end - a.end);

    // n'injecte pas si la fonction a déjà `const t = useT()`
    for (const e of all) {
      if (e.text === "\n  const t = useT();") {
        const after = out.slice(e.start, e.start + 400);
        if (/^\s*const t = useT\(\);/.test(after)) continue;
      }
      out = out.slice(0, e.start) + e.text + out.slice(e.end);
    }

    if (usesT && !src.includes('from "@/lib/i18n"')) {
      const anchor = out.match(/^import [^\n]+ from "@\/lib\/[^"]+";\n/m) ?? out.match(/^import [^\n]+;\n(?!import)/m);
      if (anchor) out = out.replace(anchor[0], anchor[0] + 'import { useT } from "@/lib/i18n";\n');
      else out = out.replace(/("use client";\n\n)/, '$1import { useT } from "@/lib/i18n";\n');
    }

    filesTouched++;
    if (!DRY) writeFileSync(file, out, "utf8");
  }
}

// dictionnaires
function appendKeys(file, lang, closing) {
  const path = join(ROOT, "lib", "i18n", file);
  let s = readFileSync(path, "utf8");
  const lines = [];
  for (const [key, v] of newKeys) {
    if (s.includes(`"${key}":`)) continue;
    lines.push(`  ${JSON.stringify(key)}: ${JSON.stringify(v[lang])},`);
  }
  if (lines.length === 0) return 0;
  s = s.replace(closing, "\n" + lines.join("\n") + "\n" + closing);
  if (!DRY) writeFileSync(path, s, "utf8");
  return lines.length;
}
const addedFr = appendKeys("fr.ts", "fr", "} as const;");
const addedEn = appendKeys("en.ts", "en", "};\n");

console.log(`${replaced} remplacements dans ${filesTouched} fichiers${DRY ? " (simulation)" : ""}`);
console.log(`${addedFr} clés ajoutées à fr.ts, ${addedEn} à en.ts`);
if (manual.length) {
  console.log(`\n${manual.length} cas à traiter à la main :`);
  for (const m of manual) console.log("  " + m);
}
