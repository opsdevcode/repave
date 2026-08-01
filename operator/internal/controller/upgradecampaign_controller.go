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
	"github.com/opsdevcode/repave/operator/internal/campaign"
	"github.com/opsdevcode/repave/operator/internal/remediation"
	"github.com/opsdevcode/repave/operator/internal/status"
)

// UpgradeCampaignReconciler tracks fleet rollout capacity for bounded remediation PRs.
type UpgradeCampaignReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=repave.dev,resources=upgradecampaigns,verbs=get;list;watch;update;patch
// +kubebuilder:rbac:groups=repave.dev,resources=upgradecampaigns/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=repave.dev,resources=goldenpathrepos,verbs=get;list;watch

func (r *UpgradeCampaignReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	var uc repavev1beta1.UpgradeCampaign
	if err := r.Get(ctx, req.NamespacedName, &uc); err != nil {
		if errors.IsNotFound(err) {
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	openCount, failures, err := r.summarize(ctx, &uc)
	if err != nil {
		return ctrl.Result{}, err
	}

	phase := repavev1beta1.UpgradeCampaignPhaseActive
	if uc.Spec.Paused {
		phase = repavev1beta1.UpgradeCampaignPhasePaused
	} else if uc.Spec.StopAfterConsecutiveGateFailures > 0 &&
		failures >= uc.Spec.StopAfterConsecutiveGateFailures {
		phase = repavev1beta1.UpgradeCampaignPhaseStopped
	}

	base := uc.DeepCopy()
	uc.Status.ObservedGeneration = uc.Generation
	uc.Status.OpenPRCount = openCount
	uc.Status.ConsecutiveGateFailures = failures
	uc.Status.Phase = phase

	ready := metav1.ConditionTrue
	reason := status.ReasonReconcileSuccess
	message := "campaign active"
	switch phase {
	case repavev1beta1.UpgradeCampaignPhasePaused:
		ready = metav1.ConditionFalse
		reason = status.ReasonCampaignPaused
		message = "campaign paused"
	case repavev1beta1.UpgradeCampaignPhaseStopped:
		ready = metav1.ConditionFalse
		reason = status.ReasonCampaignStopped
		message = "campaign stopped after consecutive remediation failures"
	}
	status.SetGoldenPathRepoCondition(&uc.Status.Conditions, metav1.Condition{
		Type:    repavev1beta1.UpgradeCampaignConditionReady,
		Status:  ready,
		Reason:  reason,
		Message: message,
	})

	if err := r.Status().Patch(ctx, &uc, client.MergeFrom(base)); err != nil {
		logger.Error(err, "unable to update UpgradeCampaign status")
		return ctrl.Result{}, err
	}
	return ctrl.Result{}, nil
}

func (r *UpgradeCampaignReconciler) summarize(
	ctx context.Context,
	uc *repavev1beta1.UpgradeCampaign,
) (openCount int32, consecutiveFailures int32, err error) {
	var repos repavev1beta1.GoldenPathRepoList
	if err := r.List(ctx, &repos, client.InNamespace(uc.Namespace)); err != nil {
		return 0, 0, err
	}

	for i := range repos.Items {
		repo := &repos.Items[i]
		matched, matchErr := campaign.MatchGoldenPathRepo(uc, repo)
		if matchErr != nil {
			return 0, 0, matchErr
		}
		if !matched {
			continue
		}
		if repo.Status.RemediationPR != nil && repo.Status.RemediationPR.State == remediation.PRStateOpen {
			openCount++
		}
		if metaFailure, _ := latestRemediationFailure(repo); metaFailure {
			consecutiveFailures++
		}
	}
	return openCount, consecutiveFailures, nil
}

func latestRemediationFailure(repo *repavev1beta1.GoldenPathRepo) (bool, string) {
	for _, cond := range repo.Status.Conditions {
		if cond.Type != status.ConditionRemediationPR {
			continue
		}
		if cond.Status == metav1.ConditionFalse && cond.Reason == status.ReasonRemediationFailed {
			return true, cond.Message
		}
	}
	return false, ""
}

func (r *UpgradeCampaignReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&repavev1beta1.UpgradeCampaign{}).
		Complete(r)
}
