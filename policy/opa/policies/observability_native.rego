# Native observability artifacts (JSON/YAML) — not Terraform plan input.
package main

_has_managed_by_tag(tags) {
    tags[_] == "managed-by:repave"
}

deny[msg] {
    input.name
    input.type
    not input.message
    msg := "datadog monitor must include message"
}

deny[msg] {
    input.name
    input.type
    tags := input.tags
    not _has_managed_by_tag(tags)
    msg := sprintf("datadog monitor %s missing managed-by:repave tag", [input.name])
}

deny[msg] {
    input.title
    input.uid
    tags := input.tags
    not _has_managed_by_tag(tags)
    msg := sprintf("grafana dashboard %s missing managed-by:repave tag", [input.title])
}

deny[msg] {
    input.title
    input.layout_type
    tags := input.tags
    not _has_managed_by_tag(tags)
    msg := sprintf("datadog dashboard %s missing managed-by:repave tag", [input.title])
}
