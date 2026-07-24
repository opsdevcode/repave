package controller

import (
	"context"

	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/github"
	"github.com/opsdevcode/repave/operator/internal/pins"
	"github.com/opsdevcode/repave/operator/internal/repave"
	"github.com/opsdevcode/repave/operator/internal/status"
)

// GoldenPathRepoReconciler reconciles a GoldenPathRepo object.
type GoldenPathRepoReconciler struct {
	client.Client
	Scheme *runtime.Scheme

	PlanUpgrader  repave.PlanUpgrader
	ApplyUpgrader repave.ApplyUpgrader
	GitHub        github.Client
	RepaveConfig  repave.Config
	GitHubToken   string
}

// +kubebuilder:rbac:groups=repave.dev,resources=goldenpathrepos,verbs=get;list;watch;update;patch
// +kubebuilder:rbac:groups=repave.dev,resources=goldenpathrepos/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=repave.dev,resources=goldenpathrepos/finalizers,verbs=update
// +kubebuilder:rbac:groups=repave.dev,resources=blueprints,verbs=get;list;watch

// Reconcile observes repave.yaml pins and updates inventory status (v1.17 slice 1+).
func (r *GoldenPathRepoReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	var repo repavev1alpha1.GoldenPathRepo
	if err := r.Get(ctx, req.NamespacedName, &repo); err != nil {
		if errors.IsNotFound(err) {
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	if requeue, err := handleGoldenPathRepoDeletion(ctx, r.Client, &repo); err != nil {
		return ctrl.Result{}, err
	} else if requeue {
		return ctrl.Result{}, nil
	}

	if requeue, err := ensureRemediationFinalizer(ctx, r.Client, &repo); err != nil {
		return ctrl.Result{}, err
	} else if requeue {
		return ctrl.Result{Requeue: true}, nil
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

	desired, err := pins.EffectiveDesired(ctx, r.Client, &repo)
	if err != nil {
		msg := err.Error()
		if patchErr := patchGoldenPathRepoStatus(ctx, r.Client, &repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			latest.Status.Phase = repavev1alpha1.GoldenPathRepoPhaseError
			latest.Status.Message = msg
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionInvalidSpec,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonSpecInvalid,
				Message: msg,
			})
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionReady,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonSpecInvalid,
				Message: msg,
			})
		}); patchErr != nil {
			return ctrl.Result{}, patchErr
		}
		return ctrl.Result{}, nil
	}

	if err := applyInventoryStatus(ctx, r.Client, &repo, desired); err != nil {
		return ctrl.Result{}, err
	}

	if err := r.Get(ctx, req.NamespacedName, &repo); err != nil {
		return ctrl.Result{}, err
	}

	upgrader := r.PlanUpgrader
	if upgrader == nil {
		upgrader = repave.CLIPlanUpgrader{}
	}
	if err := applyUpgradePlanStatus(ctx, r.Client, &repo, upgrader, r.RepaveConfig, desired); err != nil {
		return ctrl.Result{}, err
	}

	if err := r.Get(ctx, req.NamespacedName, &repo); err != nil {
		return ctrl.Result{}, err
	}

	applier := r.ApplyUpgrader
	if applier == nil {
		applier = repave.CLIApplyUpgrader{}
	}
	if err := applyRemediationPRStatus(
		ctx,
		r.Client,
		&repo,
		applier,
		r.GitHub,
		r.RepaveConfig,
		r.GitHubToken,
		desired,
	); err != nil {
		return ctrl.Result{}, err
	}

	logger.Info("reconciled GoldenPathRepo", "name", req.Name)
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
		Watches(
			&repavev1alpha1.Blueprint{},
			blueprintWatchHandler(r),
		).
		Complete(r)
}
