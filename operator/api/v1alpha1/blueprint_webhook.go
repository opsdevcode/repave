package v1alpha1

import (
	ctrl "sigs.k8s.io/controller-runtime"
)

// SetupWebhookWithManager registers the conversion webhook for Blueprint.
func (r *Blueprint) SetupWebhookWithManager(mgr ctrl.Manager) error {
	return ctrl.NewWebhookManagedBy(mgr).
		For(r).
		Complete()
}
