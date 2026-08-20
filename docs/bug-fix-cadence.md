# Bug-fix cadence

Feature work on `main` is the default. Defects still accumulate in auth, portal
HTTP handling, operator context, and assistant reads unless they are scheduled
the same way features are. This cadence keeps **fix slices** on a clock instead
of waiting for a whole-repo review.

Related: [CONTRIBUTING.md](../CONTRIBUTING.md), [v3 development](v3-development.md).

## Two loops

| Loop | When | Scope | Outcome |
| --- | --- | --- | --- |
| **Surface sweep** | After every `feat:` PR merges | Only paths that PR touched | P1/P2 as `fix/*` PRs before the next feat; P3 listed, not mixed in |
| **Estate pass** | After **three** merged feature PRs, or **weekly**, whichever comes first | Cross-cutting (portal fetch/`ok`, operator `ctx`, publish success predicates, assistant ranking, XSS) | One review note → sliced `fix(engine)`, `fix(operator)`, `fix(portal)` PRs |

Do not start the next feature while a **P1** from the last sweep is still open,
unless the user explicitly defers it.

Do not fold the next feature into a fix PR.

## Severity

| Class | Meaning | Timing |
| --- | --- | --- |
| **P1** | Authz bypass, false success, data leak, hung operator on cancel | Same day; own `fix:` PR |
| **P2** | Wrong empty UI, silent skip, missing timeout, XSS on operator-controlled strings | Next PR after the feat; still `fix:`, not the next `feat:` |
| **P3** | Copy, unused helpers, docs drift | Estate pass or docs housecleaning |

`fix:` still patches the engine tag via Release. That is intended.

## Surface sweep checklist

Walk the files in the merged feat (not the whole tree):

- **Auth** — second check after middleware (Bearer vs session); `next` / redirects; Basic on Terraform HTTP state
- **HTTP clients** — `context` / timeouts; do not use `http.DefaultClient` for upgrade or notify
- **HTTP UI** — `response.ok` before `json()`; 401/403/404 stop polling with a message
- **DOM** — no `innerHTML` for blueprint ids, run names, org-scan snippets
- **Success predicates** — treat “gates failed” as failure even if the string also looks successful
- **Reads / ranking** — first-N by URL starves later hits; paginate then filter; log parse skips
- **Forms** — first `type="submit"` is Apply, not a hidden Plan button

## Estate pass

Same checklist, repo-wide, plus:

- Operator watches that swallow `List` errors
- Fleet JSONL `continue` without a log line
- Portal inventory endpoints that look like empty catalogs on 5xx
- Roadmap **In progress** vs what actually shipped (not **Current release**)

Ship findings as **small PRs by area** (engine, operator, portal), not one
kitchen-sink branch.

## Agent / PR “What’s next”

After a **feature** PR opens or merges, the default next task is the **surface
sweep**, not the next roadmap feat. After a **fix** PR from that sweep, the
default next task is remaining P2 from the same note, then the estate pass if
the three-feat or weekly trigger fired.

Full “What’s next” shape stays in [CONTRIBUTING](../CONTRIBUTING.md#pull-requests).
