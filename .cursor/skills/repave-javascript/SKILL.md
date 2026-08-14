---
name: repave-javascript
description: >-
  JavaScript development anywhere in opsdevcode/repave: portal repave.js, ESLint,
  XSS-safe DOM patterns, and Node ESM configs. Use when editing .js/.mjs/.cjs files,
  portal static assets, commitlint config, or fixing JS lint CI.
---

# repave JavaScript development

**Scope:** all JavaScript in the monorepo (`engine/.../static/repave.js`, `.github/*.mjs`, any future `.js` paths).

Follow **`.cursor/rules/javascript-standards.mdc`** and **`.cursor/rules/javascript-security.mdc`**.

## Source of truth

| Topic | Location |
|-------|----------|
| ESLint flat config | `eslint.config.js`, `package.json` |
| Portal behavior | `.cursor/rules/portal-ui-behavior.mdc` |
| Portal copy | `.cursor/rules/portal-ux-copy.mdc` |
| Deep reference | [reference.md](reference.md) |
| Contributing | `CONTRIBUTING.md` |

## Quality workflow

```bash
npm ci              # first time / after package.json changes
make js-lint        # eslint on repo JS
make test-fast      # includes portal HTTP tests (test_api.py)
```

CI runs **`npm ci && npm run lint:js`** in **Python quality and security** when `ci_needed` is true.

## Portal (`repave.js` + page modules)

- Shared bundle loaded with **`defer`** from `templates/base.html`.
- Initialization on **`DOMContentLoaded`**; feature entrypoints **`init*`** functions.
- **`window.repavePortal`**: `saveLastRun`, `renderLastRun`, `showToast` — keep API stable for templates.
- Page-scoped native ES modules (for example `repave-home.mjs`) load from template `{% block scripts %}` only on pages that need them; may expose a small page global such as **`window.repaveHome`**.
- Stepper / dry-run / apply flows must stay aligned with **`engine/tests/test_api.py`** and **portal-ui-behavior** rule.

## Security (summary)

- No **`eval`** / dynamic code execution.
- Minimize **`innerHTML`**; escape or use **`textContent`** for dynamic strings (blueprint ids, labels).
- Storage: non-sensitive UI state only; try/catch on **`localStorage` / `sessionStorage`**.

See **[reference.md](reference.md)** for DOM XSS checklist and ESLint rule mapping.

## Related

- Python in same repo: `.cursor/skills/repave-python/SKILL.md`
- Hosted Backstage (`backstage/`): `.cursor/skills/repave-backstage/SKILL.md`
- Monorepo: `~/.cursor/skills/repave/SKILL.md`
