# Terraform plan policy: block destructive deletes without replacement.
package terraform.plan

create_in_actions(actions) {
    actions[_] == "create"
}

deny[msg] {
    change := input.resource_changes[_]
    change.change.actions[_] == "delete"
    not create_in_actions(change.change.actions)
    msg := sprintf("destructive delete without replacement: %s", [change.address])
}
