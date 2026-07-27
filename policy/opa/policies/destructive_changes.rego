# Terraform plan policy: block destructive deletes without replacement.
package terraform.plan

deny[msg] {
    change := input.resource_changes[_]
    "delete" in change.change.actions
    not "create" in change.change.actions
    msg := sprintf("destructive delete without replacement: %s", [change.address])
}
