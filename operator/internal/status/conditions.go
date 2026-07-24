package status

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/api/meta"
)

// Standard condition types for GoldenPathRepo (Kubernetes API conventions).
const (
	ConditionReady          = "Ready"
	ConditionInvalidSpec    = "InvalidSpec"
	ConditionDriftDetected  = "DriftDetected"
	ConditionUpgradePlanned = "UpgradePlanned"
	ConditionRemediationPR  = "RemediationPR"
)

// Standard condition reasons.
const (
	ReasonReconcileSuccess      = "ReconcileSuccess"
	ReasonSpecInvalid           = "SpecInvalid"
	ReasonPinsAligned           = "PinsAligned"
	ReasonPinsDrift             = "PinsDrift"
	ReasonProvenanceReadFailed  = "ProvenanceReadFailed"
	ReasonRemoteRepoUnsupported = "RemoteRepoUnsupported"
	ReasonUpgradeDiffComputed   = "UpgradeDiffComputed"
	ReasonUpgradePlanFailed     = "UpgradePlanFailed"
	ReasonUpgradePlanSkipped      = "UpgradePlanSkipped"
	ReasonUpgradePlanCleared      = "UpgradePlanCleared"
	ReasonRemediationDisabled     = "RemediationDisabled"
	ReasonRemediationPending      = "RemediationPending"
	ReasonRemediationSkipped      = "RemediationSkipped"
	ReasonRemediationPlanned      = "RemediationPlanned"
	ReasonRemediationPROpen       = "RemediationPROpen"
	ReasonRemediationFailed       = "RemediationFailed"
	ReasonRemediationCleared        = "RemediationCleared"
)

// SetGoldenPathRepoCondition updates or inserts a condition on status.
func SetGoldenPathRepoCondition(conditions *[]metav1.Condition, condition metav1.Condition) {
	meta.SetStatusCondition(conditions, condition)
}
