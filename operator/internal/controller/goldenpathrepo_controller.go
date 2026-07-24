package controller

import (
	"context"
	"fmt"

	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/status"
)

// GoldenPathRepoReconciler reconciles a GoldenPathRepo object.
type GoldenPathRepoReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=repave.dev,resources=goldenpathrepos,verbs=get;list;watch;update;patch
// +kubebuilder:rbac:groups=repave.dev,resources=goldenpathrepos/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=repave.dev,resources=goldenpathrepos/finalizers,verbs=update

// Reconcile sets baseline status for slice 0; inventory and PR logic follow in v1.17 slices 1–3.
func (r *GoldenPathRepoReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	var repo repavev1alpha1.GoldenPathRepo
	if err := r.Get(ctx, req.NamespacedName, &repo); err != nil {
		if errors.IsNotFound(err) {
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	if repo.Spec.RepoURL == "" && repo.Spec.LocalPath == "" {
		if err := patchGoldenPathRepoStatus(ctx, r.Client, &repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			latest.Status.Phase = repavev1alpha1.GoldenPathRepoPhaseError
			latest.Status.Message = "spec.repoURL or spec.localPath is required"
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionInvalidSpec,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonSpecInvalid,
				Message: latest.Status.Message,
			})
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionReady,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonSpecInvalid,
				Message: latest.Status.Message,
			})
		}); err != nil {
			return ctrl.Result{}, err
		}
		return ctrl.Result{}, nil
	}

	msg := fmt.Sprintf(
		"operator scaffold: registered %q (inventory in slice 1)",
		displayLocation(repo.Spec),
	)
	if err := patchGoldenPathRepoStatus(ctx, r.Client, &repo, func(latest *repavev1alpha1.GoldenPathRepo) {
		latest.Status.Phase = repavev1alpha1.GoldenPathRepoPhaseReady
		latest.Status.Message = msg
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionReady,
			Status:  metav1.ConditionTrue,
			Reason:  status.ReasonReconcileSuccess,
			Message: msg,
		})
	}); err != nil {
		return ctrl.Result{}, err
	}

	logger.Info("reconciled GoldenPathRepo", "phase", repavev1alpha1.GoldenPathRepoPhaseReady, "name", req.Name)
	return ctrl.Result{}, nil
}

func displayLocation(spec repavev1alpha1.GoldenPathRepoSpec) string {
	if spec.LocalPath != "" {
		return spec.LocalPath
	}
	return spec.RepoURL
}

// SetupWithManager registers the reconciler with the Manager.
func (r *GoldenPathRepoReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&repavev1alpha1.GoldenPathRepo{}).
		Complete(r)
}
