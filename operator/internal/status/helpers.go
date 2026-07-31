package status

import metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

// HasConditionType reports whether conditions include the given type.
func HasConditionType(conditions []metav1.Condition, condType string) bool {
	for _, c := range conditions {
		if c.Type == condType {
			return true
		}
	}
	return false
}
