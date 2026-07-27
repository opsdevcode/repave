# Monitor packs

Curated community monitor layouts vendored under this directory and referenced from
`observability/catalog.json` (`monitor_packs`). Each pack includes the blueprint
baseline (service down + optional SLO rules) plus the files listed in the catalog entry.

Templates use Jinja2 and the same Copier context as `monitors-as-code-generic`.
