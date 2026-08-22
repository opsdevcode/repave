package controller

import (
	"context"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/campaign"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/inventory"
	fleetmetrics "github.com/opsdevcode/repave/operator/internal/metrics"
	"github.com/opsdevcode/repave/operator/internal/notify"
	"github.com/opsdevcode/repave/operator/internal/status"
)

// materializeWorkspace resolves the repo to a local path, cloning remotes. A nil workspace
// with no error means the failure was recorded on status; retryAfter is non-zero when the
// cause was transient and the caller should requeue.
func materializeWorkspace(
	ctx context.Context,
	c client.Client,
	repo *repavev1beta1.GoldenPathRepo,
	fetcher inventory.RepoFetcher,
) (workspace *inventory.Workspace, retryAfter time.Duration, err error) {
	workspace, err = inventory.Materialize(ctx, repo.Spec, fetcher)
	if err == nil {
		return workspace, 0, nil
	}

	failure := inventory.ClassifyMaterializeError(err)
	if patchErr := patchObservationFailure(ctx, c, repo, failure.Reason, failure.Message); patchErr != nil {
		return nil, 0, patchErr
	}
	return nil, failure.RetryAfter, nil
}

func patchObservationFailure(
	ctx context.Context,
	c client.Client,
	repo *repavev1beta1.GoldenPathRepo,
	reason string,
	message string,
) error {
	return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
		latest.Status.ObservedPins = repavev1beta1.ObservedPins{}
		latest.Status.Phase = repavev1beta1.GoldenPathRepoPhaseError
		latest.Status.Message = message

		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionReady,
			Status:  metav1.ConditionFalse,
			Reason:  reason,
			Message: message,
		})
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionDriftDetected,
			Status:  metav1.ConditionUnknown,
			Reason:  reason,
			Message: message,
		})
	})
}

// applyInventoryStatus records observed pins and drift from an already materialized repo.
func applyInventoryStatus(
	ctx context.Context,
	c client.Client,
	repo *repavev1beta1.GoldenPathRepo,
	desired drift.PinSet,
	workspace *inventory.Workspace,
) (retryAfter time.Duration, err error) {
	observed, err := inventory.PinsFromWorkspace(workspace)
	if err != nil {
		failure := inventory.ClassifyProvenanceError(err)
		if patchErr := patchObservationFailure(
			ctx, c, repo, failure.Reason, failure.Message,
		); patchErr != nil {
			return 0, patchErr
		}
		return 0, nil
	}

	result := inventory.EvaluateObservation(repo.Spec, desired, observed, repo.Status.Phase)
	previousPhase := repo.Status.Phase
	patchErr := patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
		latest.Status.ObservedPins = result.Observed.ToObserved()
		latest.Status.Phase = result.Phase
		latest.Status.Message = result.Message
		applyDriftTimestamps(latest, previousPhase, result.Phase)
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionDriftDetected,
			Status:  result.DriftDetected,
			Reason:  result.DriftReason,
			Message: result.Message,
		})
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionReady,
			Status:  metav1.ConditionTrue,
			Reason:  result.ReadyReason,
			Message: readyMessage(result),
		})
	})
	if patchErr != nil {
		return 0, patchErr
	}
	if result.NotifyDrift {
		notify.SendGoldenPathRepoEvent(
			ctx,
			notify.EventDriftDetected,
			repo.ObjectMeta,
			repo.Spec,
			"",
			"",
			result.Message,
		)
	}
	return 0, nil
}

func readyMessage(result inventory.ObservationResult) string {
	if result.Phase == repavev1beta1.GoldenPathRepoPhaseOutOfDate {
		return "inventory complete; remediation pending"
	}
	return result.Message
}

func applyDriftTimestamps(
	repo *repavev1beta1.GoldenPathRepo,
	previousPhase repavev1beta1.GoldenPathRepoPhase,
	nextPhase repavev1beta1.GoldenPathRepoPhase,
) {
	switch {
	case nextPhase == repavev1beta1.GoldenPathRepoPhaseOutOfDate &&
		(previousPhase != repavev1beta1.GoldenPathRepoPhaseOutOfDate || repo.Status.DriftDetectedAt == nil):
		now := metav1.Now()
		repo.Status.DriftDetectedAt = &now
	case nextPhase == repavev1beta1.GoldenPathRepoPhaseReady &&
		previousPhase == repavev1beta1.GoldenPathRepoPhaseOutOfDate:
		detectedAt := campaign.DriftDetectedTime(repo)
		if !detectedAt.IsZero() {
			mttr := time.Since(detectedAt).Seconds()
			campaignName := repo.Labels[campaign.UpgradeCampaignLabel]
			fleetmetrics.RecordRemediationMTTR(repo.Namespace, campaignName, mttr)
		}
		repo.Status.DriftDetectedAt = nil
	}
}
