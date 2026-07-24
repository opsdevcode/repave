package controller

import (
	"context"
	"errors"
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/inventory"
	"github.com/opsdevcode/repave/operator/internal/status"
)

func applyInventoryStatus(
	ctx context.Context,
	c client.Client,
	repo *repavev1alpha1.GoldenPathRepo,
	desired drift.PinSet,
) error {
	observed, err := inventory.ObservePins(repo.Spec)
	if err != nil {
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			latest.Status.ObservedPins = repavev1alpha1.ObservedPins{}
			latest.Status.Phase = repavev1alpha1.GoldenPathRepoPhaseError
			latest.Status.Message = err.Error()

			reason := status.ReasonProvenanceReadFailed
			if errors.Is(err, inventory.ErrRemoteRepoNotSupported) {
				reason = status.ReasonRemoteRepoUnsupported
			}

			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionReady,
				Status:  metav1.ConditionFalse,
				Reason:  reason,
				Message: latest.Status.Message,
			})
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionDriftDetected,
				Status:  metav1.ConditionUnknown,
				Reason:  reason,
				Message: latest.Status.Message,
			})
		})
	}

	if inventory.EvaluateDesiredObserved(desired, observed) {
		msg := fmt.Sprintf(
			"observed pins differ from desired (blueprint %s@%s vs %s@%s)",
			desired.BlueprintName,
			desired.BlueprintVersion,
			observed.BlueprintName,
			observed.BlueprintVersion,
		)
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
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
	}

	msg := fmt.Sprintf("pins aligned for %q", displayLocation(repo.Spec))
	return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
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
