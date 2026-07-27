# Terraform plan policy: block destructive deletes without replacement.
import future.keywords.in

package terraform.plan

deny contains msg if {
    some change in input.resource_changes
    "delete" in change.change.actions
    not "create" in change.change.actions
    msg := sprintf("destructive delete without replacement: %s", [change.address])
}
