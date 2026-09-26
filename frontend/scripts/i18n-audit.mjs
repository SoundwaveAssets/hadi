// Inventaire des chaînes visibles non traduites, par analyse syntaxique.
// Usage : node scripts/i18n-audit.mjs [--json]
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { parse } from "@babel/parser";
import traverseModule from "@babel/traverse";

const traverse = traverseModule.default ?? traverseModule;
const ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const SCAN = ["app", "components"];

const TEXT_PROPS = new Set(["label", "title", "placeholder", "description", "hint", "aria-label", "emptyMessage", "subtitle", "note", "alt"]);
const SKIP_PROPS = new Set(["className", "href", "key", "src", "type", "name", "value", "id", "role", "rel", "target", "htmlFor", "autoComplete", "step", "min", "max", "pattern", "variant", "size", "tone", "align", "width"]);
const MSG_CALLS = new Set(["setError", "setSuccess", "setInfo", "setMessage", "extractError", "confirm", "alert"]);

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (full.endsWith(".tsx")) yield full;
  }
}

const STOPWORDS = /(le|la|les|un|une|des|du|de|et|ou|pour|sur|avec|sans|dans|pas|aucun|aucune|tous|toutes|votre|vos|ce|cette|ces|est|sont|par|en|au|aux|qui|que|à|the|a|an|of|to|for|in|on|no|not|all|your|this|is|are)/i;
const ACCENT = /[àâçéèêëîïôûùüÿœÀÂÇÉÈÊËÎÏÔÛÙ]/;
function looksLikeClasses(t) {
  const tokens = t.split(" ");
  const classy = tokens.filter((k) => /^[!\w\-\/\[\]:.%#()]+$/.test(k) && (k.includes("-") || k.includes(":") || k.includes("/")));
  return classy.length >= Math.max(1, Math.ceil(tokens.length * 0.5)) && !ACCENT.test(t) && !STOPWORDS.test(t);
}

function translatable(s) {
  const t = s.replace(/\s+/g, " ").trim();
  if (t.length < 2) return false;
  if (looksLikeClasses(t)) return false;
  if (/^(https?:|\/|#|\{|\$\{)/.test(t)) return false;
  if (!/[A-Za-zÀ-ÿ]{2,}/.test(t)) return false;
  if (/^[A-Z0-9_]+$/.test(t)) return false; // constantes techniques
  if (/^[a-z0-9\-_.]+$/.test(t) && !/[àâçéèêëîïôûù]/.test(t)) return false; // identifiants
  return true;
}

function insideT(path) {
  let p = path;
  while (p) {
    if (p.isCallExpression() && p.node.callee.type === "Identifier" && (p.node.callee.name === "t" || p.node.callee.name === "cn")) return true;
    if (p.isJSXAttribute() && SKIP_PROPS.has(p.node.name.name)) return true;
    p = p.parentPath;
  }
  return false;
}

const hits = [];
for (const base of SCAN) {
  for (const file of walk(join(ROOT, base))) {
    const src = readFileSync(file, "utf8");
    let ast;
    try {
      ast = parse(src, { sourceType: "module", plugins: ["typescript", "jsx"] });
    } catch (e) {
      console.error(`parse failed: ${file}: ${e.message}`);
      continue;
    }
    const rel = relative(ROOT, file).replaceAll("\\", "/");
    const push = (node, kind, text) => {
      if (!translatable(text)) return;
      hits.push({ file: rel, line: node.loc.start.line, start: node.start, end: node.end, kind, text: text.replace(/\s+/g, " ").trim() });
    };

    traverse(ast, {
      JSXText(path) {
        if (!insideT(path)) push(path.node, "text", path.node.value);
      },
      JSXAttribute(path) {
        const name = path.node.name.name;
        if (SKIP_PROPS.has(name)) return;
        const v = path.node.value;
        if (!v) return;
        if (v.type === "StringLiteral") {
          if (TEXT_PROPS.has(name) || translatable(v.value)) push(v, `prop:${name}`, v.value);
        } else if (v.type === "JSXExpressionContainer") {
          const e = v.expression;
          if (e.type === "StringLiteral" && !insideT(path)) push(e, `prop:${name}`, e.value);
          if (e.type === "TemplateLiteral" && e.quasis.some((q) => translatable(q.value.cooked))) push(e, `tpl:${name}`, src.slice(e.start, e.end));
        }
      },
      StringLiteral(path) {
        if (insideT(path)) return;
        const parent = path.parentPath;
        // branches de ternaires / || dans du JSX
        if ((parent.isConditionalExpression() || parent.isLogicalExpression()) && parent.findParent((p) => p.isJSXElement() || p.isJSXFragment())) {
          if (!parent.parentPath.isJSXAttribute() || !SKIP_PROPS.has(parent.parentPath.node?.name?.name)) push(path.node, "cond", path.node.value);
          return;
        }
        // arguments de setError / extractError / etc.
        if (parent.isCallExpression() && parent.node.callee.type === "Identifier" && MSG_CALLS.has(parent.node.callee.name)) {
          push(path.node, `msg:${parent.node.callee.name}`, path.node.value);
          return;
        }
        // tableaux de libellés / objets { label: "..." }
        if (parent.isObjectProperty() && ["label", "title", "description", "hint", "name"].includes(parent.node.key.name ?? parent.node.key.value)) {
          push(path.node, `obj:${parent.node.key.name ?? parent.node.key.value}`, path.node.value);
          return;
        }
        if (parent.isArrayExpression() && translatable(path.node.value) && path.node.value.split(" ").length >= 3) {
          push(path.node, "array", path.node.value);
        }
      },
      TemplateLiteral(path) {
        if (insideT(path)) return;
        if (path.parentPath.isJSXExpressionContainer() && path.node.quasis.some((q) => translatable(q.value.cooked))) {
          push(path.node, "tpl", src.slice(path.node.start, path.node.end));
        }
      },
    });
  }
}

hits.sort((a, b) => a.file.localeCompare(b.file) || a.start - b.start);

if (process.argv.includes("--json")) {
  console.log(JSON.stringify(hits, null, 2));
} else {
  let cur = "";
  for (const h of hits) {
    if (h.file !== cur) {
      cur = h.file;
      console.log(`\n== ${cur}`);
    }
    console.log(`  ${String(h.line).padStart(4)} [${h.kind}] ${h.text}`);
  }
  const files = new Set(hits.map((h) => h.file));
  console.log(`\n${hits.length} chaînes dans ${files.size} fichiers`);
}
