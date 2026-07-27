# Prometheus alerting rules YAML (native mode).
import future.keywords.in

package observability.prometheus

deny contains msg if {
    some group in input.groups
    some rule in group.rules
    rule.alert
    not rule.annotations.runbook_url
    msg := sprintf("alert %s missing runbook_url annotation", [rule.alert])
}

deny contains msg if {
    some group in input.groups
    some rule in group.rules
    rule.alert
    not rule.labels.severity
    msg := sprintf("alert %s missing severity label", [rule.alert])
}
