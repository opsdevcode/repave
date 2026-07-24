package controller

import (
	"context"
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/repave"
	"github.com/opsdevcode/repave/operator/internal/status"
)

const maxUpgradePlanPaths = 20

func applyUpgradePlanStatus(
	ctx context.Context,
	c client.Client,
	repo *repavev1alpha1.GoldenPathRepo,
	upgrader repave.PlanUpgrader,
	repaveCfg repave.Config,
	desired drift.PinSet,
) error {
	if repo.Status.Phase != repavev1alpha1.GoldenPathRepoPhaseOutOfDate {
		return clearUpgradePlanStatus(ctx, c, repo)
	}
	if repo.Spec.LocalPath == "" {
		msg := "upgrade diff requires spec.localPath until remote inventory is supported"
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			latest.Status.UpgradePlan = nil
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionUpgradePlanned,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonUpgradePlanSkipped,
				Message: msg,
			})
		})
	}
	if upgrader == nil {
		upgrader = repave.CLIPlanUpgrader{}
	}

	result, err := upgrader.PlanUpgrade(
		ctx,
		repaveCfg,
		repo.Spec.LocalPath,
		desired.BlueprintName,
	)
	if err != nil {
		msg := err.Error()
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			latest.Status.UpgradePlan = nil
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionUpgradePlanned,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonUpgradePlanFailed,
				Message: msg,
			})
		})
	}

	summary := result.Summary
	if summary == "" {
		summary = fmt.Sprintf(
			"%d file(s) differ for blueprint %s@%s",
			result.ChangedFileCount,
			result.BlueprintName,
			result.BlueprintVersion,
		)
	}

	return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
		latest.Status.UpgradePlan = &repavev1alpha1.UpgradePlan{
			ChangedFileCount: result.ChangedFileCount,
			BlueprintName:    result.BlueprintName,
			BlueprintVersion: result.BlueprintVersion,
			Added:            truncatePaths(result.Added, maxUpgradePlanPaths),
			Modified:         truncatePaths(result.Modified, maxUpgradePlanPaths),
			Removed:          truncatePaths(result.Removed, maxUpgradePlanPaths),
			Summary:          summary,
		}
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionUpgradePlanned,
			Status:  metav1.ConditionTrue,
			Reason:  status.ReasonUpgradeDiffComputed,
			Message: summary,
		})
	})
}

func clearUpgradePlanStatus(
	ctx context.Context,
	c client.Client,
	repo *repavev1alpha1.GoldenPathRepo,
) error {
	if repo.Status.UpgradePlan == nil &&
		!hasConditionType(repo.Status.Conditions, status.ConditionUpgradePlanned) {
		return nil
	}
	return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
		latest.Status.UpgradePlan = nil
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionUpgradePlanned,
			Status:  metav1.ConditionFalse,
			Reason:  status.ReasonUpgradePlanCleared,
			Message: "pins aligned; no upgrade plan",
		})
	})
}

func truncatePaths(paths []string, limit int) []string {
	if len(paths) <= limit {
		return paths
	}
	return paths[:limit]
}

func hasConditionType(conditions []metav1.Condition, condType string) bool {
	for _, c := range conditions {
		if c.Type == condType {
			return true
		}
	}
	return false
}
