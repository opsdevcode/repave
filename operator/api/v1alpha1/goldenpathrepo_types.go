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

// BlueprintRef selects a Blueprint CR whose spec pins override version fields.
type BlueprintRef struct {
	// Name is the Blueprint metadata.name in the same namespace as the GoldenPathRepo.
	// +kubebuilder:validation:MinLength=1
	Name string `json:"name"`
}

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

// UpgradePlan summarizes a dry-run re-render diff (v1.17 slice 2).
type UpgradePlan struct {
	// ChangedFileCount is added + modified + removed paths.
	// +optional
	ChangedFileCount int `json:"changedFileCount,omitempty"`

	// BlueprintName is the blueprint used for the plan render.
	// +optional
	BlueprintName string `json:"blueprintName,omitempty"`

	// BlueprintVersion is the blueprint version from the repave checkout used for render.
	// +optional
	BlueprintVersion string `json:"blueprintVersion,omitempty"`

	// Added lists new paths relative to the target repo (capped when stored on status).
	// +optional
	// +listType=set
	Added []string `json:"added,omitempty"`

	// Modified lists changed paths relative to the target repo (capped when stored on status).
	// +optional
	// +listType=set
	Modified []string `json:"modified,omitempty"`

	// Removed lists paths present locally but absent from the render (capped when stored on status).
	// +optional
	// +listType=set
	Removed []string `json:"removed,omitempty"`

	// Summary is a single-line human summary for kubectl and events.
	// +optional
	Summary string `json:"summary,omitempty"`
}

// RemediationSpec controls governed upgrade pull requests (v1.17 slice 3+).
type RemediationSpec struct {
	// Enabled requests a remediation PR when drift is detected and an upgrade plan exists.
	// +optional
	Enabled bool `json:"enabled,omitempty"`

	// DryRun applies the upgrade locally on a branch without opening a GitHub pull request.
	// +optional
	DryRun bool `json:"dryRun,omitempty"`

	// BaseBranch is the merge target for remediation PRs (default main).
	// +optional
	// +kubebuilder:validation:MaxLength=256
	BaseBranch string `json:"baseBranch,omitempty"`

	// BranchPrefix is prepended to generated upgrade branch names.
	// +optional
	// +kubebuilder:validation:MaxLength=128
	BranchPrefix string `json:"branchPrefix,omitempty"`
}

// RemediationPRStatus records the last opened or planned remediation pull request.
type RemediationPRStatus struct {
	// URL is the GitHub pull request URL when State is Open.
	// +optional
	URL string `json:"url,omitempty"`

	// Number is the GitHub pull request number when State is Open.
	// +optional
	Number int `json:"number,omitempty"`

	// Branch is the head branch for the remediation change.
	// +optional
	Branch string `json:"branch,omitempty"`

	// Title is the pull request title.
	// +optional
	Title string `json:"title,omitempty"`

	// State is Open or Planned (dry-run without GitHub).
	// +optional
	State string `json:"state,omitempty"`

	// DesiredBlueprintVersion is the spec pin this PR was created for (idempotency).
	// +optional
	DesiredBlueprintVersion string `json:"desiredBlueprintVersion,omitempty"`
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
	// When blueprintRef is set, blueprintVersion and standard* are taken from the Blueprint CR.
	// +required
	DesiredPins DesiredPins `json:"desiredPins"`

	// BlueprintRef watches catalog pin changes via a Blueprint CR (v1.17 slice 4).
	// +optional
	BlueprintRef *BlueprintRef `json:"blueprintRef,omitempty"`

	// Remediation configures governed pull requests for pin drift.
	// +optional
	Remediation RemediationSpec `json:"remediation,omitempty"`
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

	// UpgradePlan holds the latest dry-run diff when pins are out of date (slice 2+).
	// +optional
	UpgradePlan *UpgradePlan `json:"upgradePlan,omitempty"`

	// RemediationPR holds the latest remediation pull request (slice 3+).
	// +optional
	RemediationPR *RemediationPRStatus `json:"remediationPR,omitempty"`
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
