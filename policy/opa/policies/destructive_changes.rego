package main

deny[msg] {
    change := input.resource_changes[_]
    change.change.actions[_] == "delete"
    not create_in_actions(change.change.actions)
    msg := sprintf("destructive delete without replacement: %s", [change.address])
}

create_in_actions(actions) {
    actions[_] == "create"
}
