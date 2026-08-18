package v1beta1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

const (
	UpgradeCampaignPhaseActive = "Active"
	UpgradeCampaignPhasePaused = "Paused"
	UpgradeCampaignPhaseStopped = "Stopped"

	UpgradeCampaignConditionReady = "Ready"
)

// UpgradeCampaignSpec defines a bounded fleet upgrade rollout.
type UpgradeCampaignSpec struct {
	// Paused stops opening new remediation PRs until cleared.
	// +optional
	Paused bool `json:"paused,omitempty"`

	// MaxConcurrentPRs caps open remediation PRs for matched GoldenPathRepos.
	// Defaults to 5 when unset or zero.
	// +optional
	// +kubebuilder:validation:Minimum=1
	MaxConcurrentPRs *int32 `json:"maxConcurrentPRs,omitempty"`

	// Selector limits GoldenPathRepos governed by this campaign (same namespace).
	// An empty selector matches all GoldenPathRepos labeled with
	// repave.dev/upgrade-campaign=<metadata.name>.
	// +optional
	Selector *metav1.LabelSelector `json:"selector,omitempty"`

	// BlueprintName, when set, only matches repos whose desired blueprint name equals this value.
	// +optional
	BlueprintName string `json:"blueprintName,omitempty"`

	// StopAfterConsecutiveGateFailures halts the campaign after this many consecutive
	// remediation failures across matched repos. Zero disables the stop condition.
	// +optional
	StopAfterConsecutiveGateFailures int32 `json:"stopAfterConsecutiveGateFailures,omitempty"`
}

// UpgradeCampaignStatus reports rollout progress for the campaign.
type UpgradeCampaignStatus struct {
	// ObservedGeneration reflects the metadata.generation last reconciled.
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// Phase is Active, Paused, or Stopped.
	// +optional
	Phase string `json:"phase,omitempty"`

	// OpenPRCount is the number of matched GoldenPathRepos with open remediation PRs.
	// +optional
	OpenPRCount int32 `json:"openPRCount,omitempty"`

	// OutOfDateCount is the number of matched GoldenPathRepos with pin drift.
	// +optional
	OutOfDateCount int32 `json:"outOfDateCount,omitempty"`

	// OldestDriftAgeSeconds is the age in seconds of the longest-running drift
	// among matched repos (zero when none are out of date).
	// +optional
	OldestDriftAgeSeconds int64 `json:"oldestDriftAgeSeconds,omitempty"`

	// AverageRemediationMTTRSeconds is the mean time-to-resolve drift across matched
	// repos that returned to Ready during the last reconcile window.
	// +optional
	AverageRemediationMTTRSeconds int64 `json:"averageRemediationMTTRSeconds,omitempty"`

	// ConsecutiveGateFailures counts recent remediation failures while Active.
	// +optional
	ConsecutiveGateFailures int32 `json:"consecutiveGateFailures,omitempty"`

	// GitHubRateLimitRemaining is the last observed REST quota for the installation.
	// +optional
	GitHubRateLimitRemaining *int32 `json:"githubRateLimitRemaining,omitempty"`

	// GitHubRateLimitResetAt is when the REST quota resets (from X-RateLimit-Reset).
	// +optional
	GitHubRateLimitResetAt *metav1.Time `json:"githubRateLimitResetAt,omitempty"`

	// Conditions describe operability of the campaign.
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:storageversion
// +kubebuilder:resource:path=upgradecampaigns,shortName=uc
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="OpenPRs",type=integer,JSONPath=`.status.openPRCount`
// +kubebuilder:printcolumn:name="OutOfDate",type=integer,JSONPath=`.status.outOfDateCount`
// +kubebuilder:printcolumn:name="OldestDrift",type=integer,JSONPath=`.status.oldestDriftAgeSeconds`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// UpgradeCampaign bounds concurrent operator remediation PRs across a fleet slice.
type UpgradeCampaign struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   UpgradeCampaignSpec   `json:"spec,omitempty"`
	Status UpgradeCampaignStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// UpgradeCampaignList contains a list of UpgradeCampaign.
type UpgradeCampaignList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []UpgradeCampaign `json:"items"`
}
