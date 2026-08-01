package controller

import (
	"context"
	"fmt"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/campaign"
	fleetmetrics "github.com/opsdevcode/repave/operator/internal/metrics"
	"github.com/opsdevcode/repave/operator/internal/notify"
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

	now := time.Now()
	summary, err := r.summarize(ctx, &uc, now)
	if err != nil {
		return ctrl.Result{}, err
	}

	previousPhase := uc.Status.Phase
	previousOutOfDate := uc.Status.OutOfDateCount
	previousOpenPRs := uc.Status.OpenPRCount

	phase := repavev1beta1.UpgradeCampaignPhaseActive
	if uc.Spec.Paused {
		phase = repavev1beta1.UpgradeCampaignPhasePaused
	} else if uc.Spec.StopAfterConsecutiveGateFailures > 0 &&
		summary.ConsecutiveGateFailures >= uc.Spec.StopAfterConsecutiveGateFailures {
		phase = repavev1beta1.UpgradeCampaignPhaseStopped
	}

	base := uc.DeepCopy()
	uc.Status.ObservedGeneration = uc.Generation
	uc.Status.OpenPRCount = summary.OpenPRCount
	uc.Status.OutOfDateCount = summary.OutOfDateCount
	uc.Status.OldestDriftAgeSeconds = summary.OldestDriftAgeSeconds
	uc.Status.AverageRemediationMTTRSeconds = summary.AverageRemediationMTTRSeconds
	uc.Status.ConsecutiveGateFailures = summary.ConsecutiveGateFailures
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

	fleetmetrics.RecordCampaignSnapshot(
		uc.Namespace,
		uc.Name,
		summary.OutOfDateCount,
		summary.OldestDriftAgeSeconds,
		summary.OpenPRCount,
	)
	r.notifyCampaignChanges(&uc, summary, previousPhase, previousOutOfDate, previousOpenPRs)

	return ctrl.Result{}, nil
}

func (r *UpgradeCampaignReconciler) summarize(
	ctx context.Context,
	uc *repavev1beta1.UpgradeCampaign,
	now time.Time,
) (campaign.FleetSummary, error) {
	var repos repavev1beta1.GoldenPathRepoList
	if err := r.List(ctx, &repos, client.InNamespace(uc.Namespace)); err != nil {
		return campaign.FleetSummary{}, err
	}
	return campaign.SummarizeMatchedRepos(uc, repos.Items, now)
}

func (r *UpgradeCampaignReconciler) notifyCampaignChanges(
	uc *repavev1beta1.UpgradeCampaign,
	summary campaign.FleetSummary,
	previousPhase string,
	previousOutOfDate int32,
	previousOpenPRs int32,
) {
	switch {
	case uc.Status.Phase == repavev1beta1.UpgradeCampaignPhasePaused &&
		previousPhase != repavev1beta1.UpgradeCampaignPhasePaused:
		notify.SendCampaignEvent(
			notify.EventCampaignPaused,
			uc,
			summary,
			"campaign paused; new remediation PRs will not open",
		)
	case uc.Status.Phase == repavev1beta1.UpgradeCampaignPhaseStopped &&
		previousPhase != repavev1beta1.UpgradeCampaignPhaseStopped:
		notify.SendCampaignEvent(
			notify.EventCampaignStopped,
			uc,
			summary,
			"campaign stopped after consecutive remediation gate failures",
		)
	case uc.Status.Phase == repavev1beta1.UpgradeCampaignPhaseActive &&
		previousPhase == repavev1beta1.UpgradeCampaignPhasePaused:
		notify.SendCampaignEvent(
			notify.EventCampaignResumed,
			uc,
			summary,
			"campaign resumed; remediation PRs may open again",
		)
	}

	maxConcurrent := campaign.DefaultMaxConcurrentPRs
	if uc.Spec.MaxConcurrentPRs != nil && *uc.Spec.MaxConcurrentPRs > 0 {
		maxConcurrent = *uc.Spec.MaxConcurrentPRs
	}
	if summary.OpenPRCount >= maxConcurrent && previousOpenPRs < maxConcurrent {
		notify.SendCampaignEvent(
			notify.EventCampaignCapacityReached,
			uc,
			summary,
			fmt.Sprintf("open remediation PRs reached cap (%d)", maxConcurrent),
		)
	}

	if summary.OutOfDateCount != previousOutOfDate || summary.OpenPRCount != previousOpenPRs {
		notify.SendCampaignEvent(
			notify.EventCampaignSummary,
			uc,
			summary,
			fmt.Sprintf(
				"%d repos out of date, %d open remediation PRs",
				summary.OutOfDateCount,
				summary.OpenPRCount,
			),
		)
	}
}

func (r *UpgradeCampaignReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&repavev1beta1.UpgradeCampaign{}).
		Watches(
			&repavev1beta1.GoldenPathRepo{},
			upgradeCampaignWatchHandler(r),
		).
		Complete(r)
}
