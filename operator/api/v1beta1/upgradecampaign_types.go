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

	// ConsecutiveGateFailures counts recent remediation failures while Active.
	// +optional
	ConsecutiveGateFailures int32 `json:"consecutiveGateFailures,omitempty"`

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

func init() {
	SchemeBuilder.Register(&UpgradeCampaign{}, &UpgradeCampaignList{})
}
