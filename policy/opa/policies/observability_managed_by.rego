# Terraform plan policy: observability repos must tag managed-by:repave on monitors/dashboards.
package terraform.plan

_managed_by_tag(tags) {
    tags[_] == "managed-by:repave"
}

deny[msg] {
    change := input.resource_changes[_]
    change.type == "datadog_monitor"
    tags := change.change.after.tags
    not _managed_by_tag(tags)
    msg := sprintf("datadog_monitor %s missing managed-by:repave tag", [change.address])
}

deny[msg] {
    change := input.resource_changes[_]
    change.type == "grafana_dashboard"
    config := json.unmarshal(change.change.after.config_json)
    tags := config.tags
    not _managed_by_tag(tags)
    msg := sprintf("grafana_dashboard %s missing managed-by:repave tag", [change.address])
}
