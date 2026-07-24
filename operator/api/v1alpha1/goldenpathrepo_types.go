package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// GoldenPathRepoPhase is a summary lifecycle phase for kubectl columns.
// Prefer status.conditions for automation and monitoring.
type GoldenPathRepoPhase string

const (
	GoldenPathRepoPhasePending   GoldenPathRepoPhase = "Pending"
	GoldenPathRepoPhaseReady     GoldenPathRepoPhase = "Ready"
	GoldenPathRepoPhaseOutOfDate GoldenPathRepoPhase = "OutOfDate"
	GoldenPathRepoPhaseError     GoldenPathRepoPhase = "Error"
)

// DesiredPins are blueprint and standard versions the repo should match.
type DesiredPins struct {
	// BlueprintName is the golden path name (for example terraform-module-generic).
	// +kubebuilder:validation:MinLength=1
	BlueprintName string `json:"blueprintName"`

	// BlueprintVersion is the semver of the blueprint at generation or desired upgrade.
	// +kubebuilder:validation:MinLength=1
	BlueprintVersion string `json:"blueprintVersion"`

	// StandardSource is the in-repo or URI path to the pinned standard corpus.
	// +kubebuilder:validation:MinLength=1
	StandardSource string `json:"standardSource"`

	// StandardVersion is the semver of the standard corpus.
	// +kubebuilder:validation:MinLength=1
	StandardVersion string `json:"standardVersion"`
}

// ObservedPins are pins read from repave.yaml on the last successful observation.
type ObservedPins struct {
	BlueprintName    string `json:"blueprintName,omitempty"`
	BlueprintVersion string `json:"blueprintVersion,omitempty"`
	StandardSource   string `json:"standardSource,omitempty"`
	StandardVersion  string `json:"standardVersion,omitempty"`
}

// GoldenPathRepoSpec defines a generated golden-path repository to reconcile.
// +kubebuilder:validation:XValidation:rule="(has(self.repoURL) && self.repoURL != '') || (has(self.localPath) && self.localPath != '')",message="either repoURL or localPath must be set"
type GoldenPathRepoSpec struct {
	// RepoURL is the git remote (https or ssh). For local development use localPath instead.
	// +optional
	// +kubebuilder:validation:MaxLength=2048
	RepoURL string `json:"repoURL,omitempty"`

	// LocalPath is an absolute filesystem path to a module repo (local dev and envtest).
	// +optional
	// +kubebuilder:validation:MaxLength=4096
	LocalPath string `json:"localPath,omitempty"`

	// DesiredPins are the target blueprint and standard versions for this repo.
	// +required
	DesiredPins DesiredPins `json:"desiredPins"`
}

// GoldenPathRepoStatus defines the observed state of GoldenPathRepo.
type GoldenPathRepoStatus struct {
	// Conditions represent the latest available observations of reconciliation state.
	// +listType=map
	// +listMapKey=type
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// Phase summarizes reconciliation state for kubectl columns.
	// +optional
	Phase GoldenPathRepoPhase `json:"phase,omitempty"`

	// Message is a human-readable detail string for the current phase.
	// +optional
	Message string `json:"message,omitempty"`

	// ObservedGeneration reflects the metadata.generation last reconciled.
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// ObservedPins holds pins read from repave.yaml when inventory runs (slice 1+).
	// +optional
	ObservedPins ObservedPins `json:"observedPins,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:path=goldenpathrepos,shortName=gpr
// +kubebuilder:printcolumn:name="Ready",type=string,JSONPath=`.status.conditions[?(@.type=="Ready")].status`
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="Repo",type=string,JSONPath=`.spec.repoURL`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// GoldenPathRepo registers a generated repository for drift and upgrade reconciliation.
type GoldenPathRepo struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   GoldenPathRepoSpec   `json:"spec,omitempty"`
	Status GoldenPathRepoStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// GoldenPathRepoList contains a list of GoldenPathRepo.
type GoldenPathRepoList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []GoldenPathRepo `json:"items"`
}

func init() {
	SchemeBuilder.Register(&GoldenPathRepo{}, &GoldenPathRepoList{})
}
