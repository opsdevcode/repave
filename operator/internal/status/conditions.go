package status

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/api/meta"
)

// Standard condition types for GoldenPathRepo (Kubernetes API conventions).
const (
	ConditionReady       = "Ready"
	ConditionInvalidSpec = "InvalidSpec"
)

// Standard condition reasons.
const (
	ReasonReconcileSuccess = "ReconcileSuccess"
	ReasonSpecInvalid      = "SpecInvalid"
)

// SetGoldenPathRepoCondition updates or inserts a condition on status.
func SetGoldenPathRepoCondition(conditions *[]metav1.Condition, condition metav1.Condition) {
	meta.SetStatusCondition(conditions, condition)
}
