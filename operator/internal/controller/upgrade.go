package controller

import (
	"context"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/inventory"
	"github.com/opsdevcode/repave/operator/internal/repave"
	"github.com/opsdevcode/repave/operator/internal/status"
)

func applyUpgradePlanStatus(
	ctx context.Context,
	c client.Client,
	repo *repavev1beta1.GoldenPathRepo,
	upgrader repave.PlanUpgrader,
	repaveCfg repave.Config,
	desired drift.PinSet,
	workspace *inventory.Workspace,
) error {
	if repo.Status.Phase != repavev1beta1.GoldenPathRepoPhaseOutOfDate {
		return clearUpgradePlanStatus(ctx, c, repo)
	}
	if workspace == nil || workspace.Path == "" {
		msg := "upgrade diff requires a materialized repository"
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
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
		upgrader = repave.NewPlanUpgrader(repaveCfg)
	}

	target, err := repave.UpgradeTarget(repo.Spec.RepoURL, repo.Spec.LocalPath, workspace.Path, repaveCfg)
	if err != nil {
		msg := err.Error()
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
			latest.Status.UpgradePlan = nil
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionUpgradePlanned,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonUpgradePlanFailed,
				Message: msg,
			})
		})
	}
	result, err := upgrader.PlanUpgrade(
		ctx,
		repaveCfg,
		target,
		desired.BlueprintName,
	)
	if err != nil {
		msg := err.Error()
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
			latest.Status.UpgradePlan = nil
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionUpgradePlanned,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonUpgradePlanFailed,
				Message: msg,
			})
		})
	}

	plan, summary := repave.BuildUpgradePlan(result)
	return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
		latest.Status.UpgradePlan = plan
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
	repo *repavev1beta1.GoldenPathRepo,
) error {
	if repo.Status.UpgradePlan == nil &&
		!status.HasConditionType(repo.Status.Conditions, status.ConditionUpgradePlanned) {
		return nil
	}
	return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
		latest.Status.UpgradePlan = nil
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionUpgradePlanned,
			Status:  metav1.ConditionFalse,
			Reason:  status.ReasonUpgradePlanCleared,
			Message: "pins aligned; no upgrade plan",
		})
	})
}
