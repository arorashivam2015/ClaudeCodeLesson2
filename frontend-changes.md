# Frontend Quality Tooling Changes

## Summary

Added Prettier and ESLint as frontend code-quality tools, applied consistent
formatting to all frontend files, and created a development script for running
quality checks.

---

## New Files

### `package.json`
Defines npm scripts and dev-dependencies for frontend tooling.

| Script | What it does |
|---|---|
| `npm run format` | Auto-format JS/CSS/HTML with Prettier |
| `npm run format:check` | Check formatting without writing files |
| `npm run lint` | Lint `frontend/script.js` with ESLint |
| `npm run lint:fix` | Auto-fix lint issues |
| `npm run quality` | Run format check + lint (CI mode) |
| `npm run quality:fix` | Auto-format + auto-fix everything |

**Dependencies added:**
- `prettier@^3` — opinionated code formatter
- `eslint@^9` — JavaScript linter
- `@eslint/js@^9` — ESLint built-in rule sets
- `eslint-config-prettier@^10` — disables ESLint rules that conflict with Prettier

---

### `.prettierrc`
Prettier configuration applied to all frontend files:

| Option | Value | Rationale |
|---|---|---|
| `printWidth` | 100 | Wider than default 80 to reduce awkward wraps in template literals |
| `tabWidth` | 2 | JS/CSS community standard (was 4-space in original) |
| `singleQuote` | false | Prettier default; HTML attribute values use double quotes |
| `trailingComma` | `"es5"` | Trailing commas in objects/arrays, not function parameters |
| `arrowParens` | `"always"` | `(e) =>` instead of `e =>` for clarity |
| `endOfLine` | `"lf"` | Consistent cross-platform line endings |

---

### `eslint.config.js`
ESLint flat-config targeting `frontend/script.js` with browser globals:

- Extends `@eslint/js` recommended rules
- Disables rules that conflict with Prettier via `eslint-config-prettier`
- Browser globals declared: `document`, `window`, `fetch`, `console`, `Date`, `marked`
- Key rules enforced: `eqeqeq`, `no-var`, `prefer-const`, `no-unused-vars`

---

### `scripts/frontend-quality.sh`
Shell script wrapping the npm quality commands.

```bash
# Check formatting and lint (no file changes)
./scripts/frontend-quality.sh

# Auto-format and fix everything
./scripts/frontend-quality.sh --fix
```

The script auto-installs `node_modules` if they are missing, then delegates
to the npm scripts defined in `package.json`.

---

## Modified Files

### `frontend/script.js`
- Indentation: 4-space → 2-space
- String quotes: single `'` → double `"` (Prettier default)
- Trailing commas added to multi-line objects and arrays
- Extra blank lines removed (double blanks collapsed to single)
- Arrow function parameter parentheses made consistent: `e =>` → `(e) =>`
- Redundant inline comments removed (e.g. `// Get DOM elements after page loads`,
  `// Disable input`, `// Add user message`, `// Update session ID if new`,
  `// Replace loading message with response/error`, `// Update stats in UI`,
  `// Update course titles`)

### `frontend/index.html`
- Indentation: 4-space → 2-space
- `DOCTYPE` lowercased to `<!doctype html>` (Prettier standard)
- Void elements self-closed with ` />`  (`<meta ... />`, `<link ... />`, `<input ... />`)
- Long `<button>` and `<input>` attribute lists wrapped one-per-line

### `frontend/style.css`
- Indentation: 4-space → 2-space
- Multi-value `transition` shorthand split onto separate lines (Prettier CSS style)
- `@keyframes` percentages grouped: `0%, 80%, 100%` selector on one line
- Selector lists with two items kept together; long selector groups kept intact
- Single-line rules (`h1 { font-size: 1.5rem; }`) expanded to multi-line blocks
- Removed stale comment `/* Remove max-height to show all titles without scrolling */`

---

## How to Use

**First-time setup** (installs Prettier + ESLint):
```bash
npm install
```

**Check quality before committing:**
```bash
./scripts/frontend-quality.sh
# or: npm run quality
```

**Auto-fix all formatting issues:**
```bash
./scripts/frontend-quality.sh --fix
# or: npm run quality:fix
```
