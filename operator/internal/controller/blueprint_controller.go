package controller

import (
	"context"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/status"
)

// BlueprintReconciler publishes Blueprint spec pins into status for fleet queries.
type BlueprintReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=repave.dev,resources=blueprints,verbs=get;list;watch;update;patch
// +kubebuilder:rbac:groups=repave.dev,resources=blueprints/status,verbs=get;update;patch

func (r *BlueprintReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	var bp repavev1beta1.Blueprint
	if err := r.Get(ctx, req.NamespacedName, &bp); err != nil {
		if errors.IsNotFound(err) {
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	base := bp.DeepCopy()
	bp.Status.ObservedGeneration = bp.Generation
	bp.Status.TargetPins = &repavev1beta1.BlueprintTargetPins{
		Version:         bp.Spec.Version,
		StandardSource:  bp.Spec.Standard.Source,
		StandardVersion: bp.Spec.Standard.Version,
	}
	status.SetGoldenPathRepoCondition(&bp.Status.Conditions, metav1.Condition{
		Type:    repavev1beta1.BlueprintConditionReady,
		Status:  metav1.ConditionTrue,
		Reason:  status.ReasonReconcileSuccess,
		Message: "Blueprint target pins published",
	})

	if err := r.Status().Patch(ctx, &bp, client.MergeFrom(base)); err != nil {
		logger.Error(err, "unable to update Blueprint status")
		return ctrl.Result{}, err
	}
	return ctrl.Result{}, nil
}

func (r *BlueprintReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&repavev1beta1.Blueprint{}).
		Complete(r)
}
