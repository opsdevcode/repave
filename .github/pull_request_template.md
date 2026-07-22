## Summary

<!-- What changed and why? Keep this focused on intent and impact. -->

## Change type

<!-- PR titles must follow Conventional Commits (validated in CI). -->

- [ ] `feat` — new feature (minor release bump)
- [ ] `fix` — bug fix (patch release bump)
- [ ] `docs` — documentation only
- [ ] `refactor` — code change without behavior change
- [ ] `test` — tests only
- [ ] `build` / `ci` / `chore` — tooling, CI, or maintenance
- [ ] breaking change (`feat!` / `fix!` or `BREAKING CHANGE:` in body)

**Suggested PR title:**

```text
<type>[optional scope]: <description>
```

## Scope

<!-- Which areas does this touch? -->

- [ ] `engine/` (generation core)
- [ ] `blueprints/`
- [ ] `schemas/` (frozen contracts)
- [ ] `deploy/`
- [ ] `docs/` / repo metadata
- [ ] other: <!-- describe -->

## Test plan

<!-- How was this verified? -->

- [ ] `cd engine && pytest`
- [ ] `make generate` (or local form flow) verified
- [ ] gates still enforced (no bypass path added)
- [ ] not run (explain why)

## Release impact

<!-- release-please uses conventional commits on merge to main. -->

- [ ] user-facing release note expected (`feat` / `fix` / breaking)
- [ ] no release bump expected (`docs`, `chore`, `ci`, etc.)

## Checklist

- [ ] PR title follows [Conventional Commits](https://www.conventionalcommits.org/)
- [ ] No cloud-specific logic added to `engine/` (cloud code stays in `blueprints/`)
- [ ] Deterministic generation preserved (same inputs → same output)
- [ ] If `schemas/` changed: breaking change called out and version/discussion handled
- [ ] Secrets/credentials are not committed or logged

## Related links

<!-- Issues, design notes, follow-ups (optional). -->

- 
