# IP assignment (send to your CTO)

**Purpose:** one page so you can invoice if they pass on using repave internally.

This is not legal advice. Have counsel review before anyone signs.

## What I am asking

If you are **not** taking repave as an employer product, I need a written **pass**
plus an **assignment** (or confirmation I own) of copyright and related rights in:

- `opsdevcode/repave` (engine, portal, operator, blueprints, Helm, GHCR artifacts)
- `opsdevcode/relay` (if in scope)

so I can sell self-hosted licenses under opsdevcode / Eric Skaggs.

## What already happened on GitHub

- Both repositories are **public** (proprietary license; GHCR remains private).
- Default-branch license is **proprietary** (not Apache-2.0 going forward).
- Historical public Apache-2.0 / BSD tags that already shipped stay under those
  licenses for people who received them. New work is not OSI-licensed.

## What I will not do without this paper

- Invoice customers
- Grant GHCR pull tokens to third parties as a product
- Represent that the employer has no claim

Until they reply, keep moving on [vendor-ops.md](vendor-ops.md) only.

## Suggested reply (copy/paste)

> We pass on using repave as a company product. We assign to Eric Skaggs all
> right, title, and interest in the repave and relay software as of [date],
> excluding third-party open-source components. Historical public releases
> remain under the licenses they shipped with.

Signed, dated, on company letterhead or an equivalent instrument counsel
approves.

## After they sign

1. Store the instrument off-repo (not in git).
2. Issue the first customer license (`python3 scripts/issue_repave_license.py`).
3. Add their GitHub org (or a machine user) as a GHCR package reader.
4. Send [install.md](install.md) and the JSON license file.
