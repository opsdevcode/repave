package controller

import (
	"context"
	"errors"
	"fmt"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/inventory"
	"github.com/opsdevcode/repave/operator/internal/notify"
	"github.com/opsdevcode/repave/operator/internal/status"
)

// remoteFetchRetry backs off after a transient clone failure (network, auth, missing ref).
const remoteFetchRetry = 2 * time.Minute

// materializeWorkspace resolves the repo to a local path, cloning remotes. A nil workspace
// with no error means the failure was recorded on status; retryAfter is non-zero when the
// cause was transient and the caller should requeue.
func materializeWorkspace(
	ctx context.Context,
	c client.Client,
	repo *repavev1alpha1.GoldenPathRepo,
	fetcher inventory.RepoFetcher,
) (workspace *inventory.Workspace, retryAfter time.Duration, err error) {
	workspace, err = inventory.Materialize(ctx, repo.Spec, fetcher)
	if err == nil {
		return workspace, 0, nil
	}

	reason := status.ReasonProvenanceReadFailed
	switch {
	case errors.Is(err, inventory.ErrRemoteRepoNotSupported):
		reason = status.ReasonRemoteRepoUnsupported
	case errors.Is(err, inventory.ErrRemoteFetchFailed):
		reason = status.ReasonRemoteFetchFailed
		retryAfter = remoteFetchRetry
	}

	if patchErr := patchObservationFailure(ctx, c, repo, reason, err.Error()); patchErr != nil {
		return nil, 0, patchErr
	}
	return nil, retryAfter, nil
}

func patchObservationFailure(
	ctx context.Context,
	c client.Client,
	repo *repavev1alpha1.GoldenPathRepo,
	reason string,
	message string,
) error {
	return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
		latest.Status.ObservedPins = repavev1alpha1.ObservedPins{}
		latest.Status.Phase = repavev1alpha1.GoldenPathRepoPhaseError
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
	repo *repavev1alpha1.GoldenPathRepo,
	desired drift.PinSet,
	workspace *inventory.Workspace,
) (retryAfter time.Duration, err error) {
	observed, err := inventory.PinsFromWorkspace(workspace)
	if err != nil {
		if patchErr := patchObservationFailure(
			ctx, c, repo, status.ReasonProvenanceReadFailed, err.Error(),
		); patchErr != nil {
			return 0, patchErr
		}
		return 0, nil
	}

	if inventory.EvaluateDesiredObserved(desired, observed) {
		msg := fmt.Sprintf(
			"observed pins differ from desired (blueprint %s@%s vs %s@%s)",
			desired.BlueprintName,
			desired.BlueprintVersion,
			observed.BlueprintName,
			observed.BlueprintVersion,
		)
		notifyDrift := repo.Status.Phase != repavev1alpha1.GoldenPathRepoPhaseOutOfDate
		patchErr := patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			latest.Status.ObservedPins = observed.ToObserved()
			latest.Status.Phase = repavev1alpha1.GoldenPathRepoPhaseOutOfDate
			latest.Status.Message = msg
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionDriftDetected,
				Status:  metav1.ConditionTrue,
				Reason:  status.ReasonPinsDrift,
				Message: msg,
			})
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionReady,
				Status:  metav1.ConditionTrue,
				Reason:  status.ReasonPinsDrift,
				Message: "inventory complete; remediation pending",
			})
		})
		if patchErr != nil {
			return 0, patchErr
		}
		if notifyDrift {
			cfg := notify.LoadConfig()
			notify.Send(cfg, notify.EventDriftDetected, notify.Payload{
				Namespace:  repo.Namespace,
				Name:       repo.Name,
				Repository: displayLocation(repo.Spec),
				Message:    msg,
			})
		}
		return 0, nil
	}

	msg := fmt.Sprintf("pins aligned for %q", displayLocation(repo.Spec))
	return 0, patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
		latest.Status.ObservedPins = observed.ToObserved()
		latest.Status.Phase = repavev1alpha1.GoldenPathRepoPhaseReady
		latest.Status.Message = msg
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionDriftDetected,
			Status:  metav1.ConditionFalse,
			Reason:  status.ReasonPinsAligned,
			Message: msg,
		})
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionReady,
			Status:  metav1.ConditionTrue,
			Reason:  status.ReasonPinsAligned,
			Message: msg,
		})
	})
}
