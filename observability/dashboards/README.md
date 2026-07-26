# Community dashboard packs

Vendored **forks** of popular Grafana.com and Datadog community dashboards live here.
Each fork is a Jinja template parameterized at generate time (`service_name`, `team`,
`environment`, etc.) and listed in `observability/catalog.json` under `dashboard_packs`.

## Adding a pack

1. Add a `.json.jinja` file under `grafana/community/` or `datadog/community/`.
2. Register the pack in `observability/catalog.json` with upstream URL and license.
3. Include required repave tags (see `standards/observability/dashboards-as-code.md`).

Do not commit full multi-megabyte upstream exports; ship a **maintainable fork** with
attribution and queries adapted to repave inputs.
