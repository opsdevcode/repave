# Terraform plan policy: observability repos must tag managed-by:repave on monitors/dashboards.
package terraform.plan

import future.keywords.in

_managed_by_tag(tags) if {
    some tag in tags
    tag == "managed-by:repave"
}

deny contains msg if {
    some change in input.resource_changes
    change.type == "datadog_monitor"
    tags := change.change.after.tags
    not _managed_by_tag(tags)
    msg := sprintf("datadog_monitor %s missing managed-by:repave tag", [change.address])
}

deny contains msg if {
    some change in input.resource_changes
    change.type == "grafana_dashboard"
    config := json.unmarshal(change.change.after.config_json)
    tags := config.tags
    not _managed_by_tag(tags)
    msg := sprintf("grafana_dashboard %s missing managed-by:repave tag", [change.address])
}
