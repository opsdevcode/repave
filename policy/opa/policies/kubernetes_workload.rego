# Kubernetes manifest checks for Helm-rendered golden paths (conftest input per document).
package kubernetes

deny[msg] {
    input.kind == "Deployment"
    not input.metadata.name
    msg := "Deployment must include metadata.name"
}
