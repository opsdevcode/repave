# RUNBOOK.md required sections (v1.81)

Generated repos that ship `RUNBOOK.md` must include these level-2 headings (exact titles).
The `docs-drift` gate enforces them when the file is present; `app-service-generic`,
`helm-chart-generic`, and `slo-as-code-generic` always emit the file.

| Section | Purpose |
| --- | --- |
| `## Owner` | Owning team and primary contact |
| `## Escalation` | On-call path and severity routing |
| `## Dashboards` | Links to service dashboards |
| `## Rollback procedure` | How to revert a bad deploy |
| `## Game-day checklist` | Pre-incident verification steps |
