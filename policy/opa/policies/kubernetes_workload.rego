# Kubernetes manifest checks for Helm-rendered golden paths (conftest input per document).
package kubernetes

deny contains msg if {
	input.kind == "Deployment"
	not input.metadata.name
	msg := "Deployment must include metadata.name"
}
