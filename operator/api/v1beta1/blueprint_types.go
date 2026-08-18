package v1beta1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// BlueprintStandardPins mirror blueprint.yaml spec.standard pin fields.
type BlueprintStandardPins struct {
	// Source is the in-repo or URI path to the standard corpus.
	// +kubebuilder:validation:MinLength=1
	Source string `json:"source"`

	// Version is the semver of the standard corpus.
	// +kubebuilder:validation:MinLength=1
	Version string `json:"version"`
}

// BlueprintSpec defines catalog pin versions for a golden path blueprint.
type BlueprintSpec struct {
	// Version is the semver of the blueprint template.
	// +kubebuilder:validation:MinLength=1
	Version string `json:"version"`

	// Standard pins the governance corpus applied at generation time.
	// +required
	Standard BlueprintStandardPins `json:"standard"`
}

const BlueprintConditionReady = "Ready"

// BlueprintStatus records the last observed spec generation and published pin target.
type BlueprintStatus struct {
	// ObservedGeneration reflects the metadata.generation last reconciled.
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// TargetPins mirrors spec pin fields for fleet queries and kubectl columns.
	// +optional
	TargetPins *BlueprintTargetPins `json:"targetPins,omitempty"`

	// Conditions describe operability of the Blueprint target.
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`
}

// BlueprintTargetPins are the fleet-wide desired pins published by this Blueprint CR.
type BlueprintTargetPins struct {
	// Version is the semver of the blueprint template.
	Version string `json:"version"`

	// StandardSource is the in-repo or URI path to the standard corpus.
	StandardSource string `json:"standardSource"`

	// StandardVersion is the semver of the standard corpus.
	StandardVersion string `json:"standardVersion"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:storageversion
// +kubebuilder:resource:path=blueprints,shortName=bp
// +kubebuilder:printcolumn:name="Version",type=string,JSONPath=`.spec.version`
// +kubebuilder:printcolumn:name="Standard",type=string,JSONPath=`.spec.standard.version`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// Blueprint mirrors repave catalog pin versions for fleet-wide desired state.
type Blueprint struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   BlueprintSpec   `json:"spec,omitempty"`
	Status BlueprintStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// BlueprintList contains a list of Blueprint.
type BlueprintList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []Blueprint `json:"items"`
}

// Hub marks Blueprint as the conversion hub (storage version).
func (*Blueprint) Hub() {}
