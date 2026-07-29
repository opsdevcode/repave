# repave JavaScript — reference

## Files

| File | Environment | Notes |
|------|-------------|--------|
| `engine/src/repave_engine/static/repave.js` | Browser | IIFE, ~1k lines, portal UX |
| `.github/commitlint.config.mjs` | Node (CI) | Conventional commit rules |

## ESLint

Root **`eslint.config.js`** (ESLint 9 flat config):

- **Browser** block: `engine/src/repave_engine/static/**/*.js`
- **Node** block: `.github/**/*.mjs`
- Ignores: `node_modules`, `engine/build/**`

Run locally:

```bash
npm ci
npm run lint:js
# or
make js-lint
```

## DOM XSS checklist

Before merging portal JS:

1. List every **`innerHTML`** / **`outerHTML`** assignment.
2. Trace data source: server template, **`sessionStorage`**, form fields, API.
3. If source can contain `<>&"'`, switch to **`textContent`** or build nodes with **`createElement`**.
4. Hrefs: build with **`encodeURIComponent`** for dynamic path segments.
5. Do not use **`document.write`** or **`javascript:`** URLs.

## Portal contracts (do not break)

- **`data-form-stepper`**, **`data-dry-run-run`**, **`data-dry-run-submit`**
- Events: **`repave:stepper-pre-submit`**, **`repave:stepper-will-submit`**, **`repave:stepper-will-advance`**, **`repave:stepper-change`**
- POST **`/generate`** with **`dry_run=true`** must remain reachable from stepper dry-run controls

## Testing

- Automated: **`engine/tests/test_api.py`** (static asset routes, form markers, dry-run smoke).
- Manual: blueprint page → **Dry run preview** → result shows file tree.

## External guidance

- [MDN Web Security](https://developer.mozilla.org/en-US/docs/Web/Security)
- [OWASP DOM based XSS](https://owasp.org/www-community/attacks/DOM_Based_XSS)
- [ESLint recommended rules](https://eslint.org/docs/latest/rules/)
