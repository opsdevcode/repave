# Observability catalog

`catalog.json` lists **notification sources** (PagerDuty, Slack, email, …) and the
**targets** available under each source. The repave portal uses this file to populate
`notification_source` and `notification_target` dropdowns on the observability golden path.

Customize targets for your estate by vendoring or overriding `observability/catalog.json`
in your repave deployment (same pattern as `policy/catalog.json`).
