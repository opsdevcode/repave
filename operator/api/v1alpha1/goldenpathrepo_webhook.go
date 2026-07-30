package v1alpha1

import (
	ctrl "sigs.k8s.io/controller-runtime"
)

// SetupWebhookWithManager registers the conversion webhook for GoldenPathRepo.
func (r *GoldenPathRepo) SetupWebhookWithManager(mgr ctrl.Manager) error {
	return ctrl.NewWebhookManagedBy(mgr).
		For(r).
		Complete()
}
