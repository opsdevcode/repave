package controller

import (
	"context"
	"errors"
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/campaign"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/inventory"
	"github.com/opsdevcode/repave/operator/internal/notify"
	"github.com/opsdevcode/repave/operator/internal/remediation"
	"github.com/opsdevcode/repave/operator/internal/repave"
	"github.com/opsdevcode/repave/operator/internal/status"
)

const goldenPathRepoFinalizer = "repave.dev/goldenpathrepo-finalizer"

func ensureRemediationFinalizer(
	ctx context.Context,
	c client.Client,
	repo *repavev1beta1.GoldenPathRepo,
) (bool, error) {
	if !repo.Spec.Remediation.Enabled {
		return false, nil
	}
	if controllerutil.ContainsFinalizer(repo, goldenPathRepoFinalizer) {
		return false, nil
	}
	base := client.MergeFrom(repo.DeepCopy())
	controllerutil.AddFinalizer(repo, goldenPathRepoFinalizer)
	if err := c.Patch(ctx, repo, base); err != nil {
		return false, err
	}
	return true, nil
}

func applyRemediationPRStatus(
	ctx context.Context,
	c client.Client,
	repo *repavev1beta1.GoldenPathRepo,
	workspace *inventory.Workspace,
	applier repave.ApplyUpgrader,
	repaveCfg repave.Config,
	githubToken string,
	desired drift.PinSet,
) error {
	if !repo.Spec.Remediation.Enabled {
		return clearRemediationPRStatus(ctx, c, repo, status.ReasonRemediationDisabled, "remediation disabled")
	}

	if repo.Status.Phase != repavev1beta1.GoldenPathRepoPhaseOutOfDate {
		return clearRemediationPRStatus(ctx, c, repo, status.ReasonRemediationCleared, "pins aligned; remediation not required")
	}

	if !meta.IsStatusConditionTrue(repo.Status.Conditions, status.ConditionUpgradePlanned) {
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationPending,
				Message: "waiting for upgrade plan before opening remediation PR",
			})
		})
	}

	decision, err := campaign.EvaluateRemediation(ctx, c, repo)
	if err != nil {
		return err
	}
	if !decision.Allowed {
		return patchRemediationPRFailed(ctx, c, repo, decision.Reason, decision.Message, false)
	}

	workDir, workErr := remediation.WorkDir(repo.Spec, workspace)
	if workErr != nil {
		return patchRemediationPRFailed(ctx, c, repo, status.ReasonRemediationSkipped, workErr.Error(), false)
	}

	desiredVersion := desired.BlueprintVersion
	if remediation.PROpen(repo.Status.RemediationPR, desiredVersion) {
		return nil
	}

	if applier == nil {
		applier = repave.NewApplyUpgrader(repaveCfg)
	}

	summary := ""
	if repo.Status.UpgradePlan != nil {
		summary = repo.Status.UpgradePlan.Summary
	}
	prMeta := remediation.BuildPRMetadata(repo.Spec.Remediation, desired, summary)

	applyResult, err := remediation.ApplyUpgradeChanges(ctx, remediation.ApplyInput{
		Spec:      repo.Spec,
		WorkDir:   workDir,
		Desired:   desired,
		Metadata:  prMeta,
		Applier:   applier,
		RepaveCfg: repaveCfg,
	})
	if err != nil {
		return patchRemediationPRFailed(ctx, c, repo, status.ReasonRemediationFailed, err.Error(), true)
	}

	if repo.Spec.Remediation.DryRun {
		msg := fmt.Sprintf("dry-run remediation on branch %s", applyResult.GitBranch)
		openedAt := metav1.Now()
		if err := patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
			latest.Status.RemediationPR = &repavev1beta1.RemediationPRStatus{
				Branch:                  applyResult.GitBranch,
				Title:                   prMeta.Title,
				State:                   remediation.PRStatePlanned,
				OpenedAt:                &openedAt,
				DesiredBlueprintVersion: desiredVersion,
			}
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionTrue,
				Reason:  status.ReasonRemediationPlanned,
				Message: msg,
			})
		}); err != nil {
			return err
		}
		notify.SendGoldenPathRepoEvent(
			ctx,
			notify.EventRemediationPRPlanned,
			repo.ObjectMeta,
			repo.Spec,
			applyResult.GitBranch,
			"",
			msg,
		)
		return nil
	}

	published, err := remediation.PublishPullRequest(ctx, remediation.PublishInput{
		Spec:           repo.Spec,
		WorkDir:        workDir,
		Metadata:       prMeta,
		ApplyResult:    applyResult,
		DesiredVersion: desiredVersion,
		GitHubToken:    githubToken,
	})
	if err != nil {
		switch {
		case errors.Is(err, remediation.ErrGitHubTokenRequired):
			return patchRemediationPRFailed(ctx, c, repo, status.ReasonRemediationPending, err.Error(), false)
		case errors.Is(err, remediation.ErrRepoURLRequired):
			return patchRemediationPRFailed(ctx, c, repo, status.ReasonRemediationSkipped, err.Error(), false)
		default:
			return patchRemediationPRFailed(ctx, c, repo, status.ReasonRemediationFailed, err.Error(), true)
		}
	}

	prState := remediation.PRStateOpen
	reason := status.ReasonRemediationPROpen
	message := published.URL
	if published.Merged {
		prState = remediation.PRStateMerged
		message = published.URL
		if published.MergeCommitSHA != "" {
			message = fmt.Sprintf("%s merged %s", published.URL, published.MergeCommitSHA)
		}
	} else if published.MergeError != "" {
		message = fmt.Sprintf("%s; auto-merge failed: %s", published.URL, published.MergeError)
	}

	if err := patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
		openedAt := metav1.Now()
		latest.Status.RemediationPR = &repavev1beta1.RemediationPRStatus{
			URL:                     published.URL,
			Number:                  published.Number,
			Branch:                  published.Branch,
			Title:                   published.Title,
			State:                   prState,
			OpenedAt:                &openedAt,
			DesiredBlueprintVersion: desiredVersion,
		}
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionRemediationPR,
			Status:  metav1.ConditionTrue,
			Reason:  reason,
			Message: message,
		})
	}); err != nil {
		return err
	}
	eventMsg := fmt.Sprintf("Remediation PR opened: %s", published.Title)
	if published.Merged {
		eventMsg = fmt.Sprintf("Remediation PR merged: %s", published.Title)
	}
	notify.SendGoldenPathRepoEvent(
		ctx,
		notify.EventRemediationPROpened,
		repo.ObjectMeta,
		repo.Spec,
		published.Branch,
		published.URL,
		eventMsg,
	)
	return nil
}

func patchRemediationPRFailed(
	ctx context.Context,
	c client.Client,
	repo *repavev1beta1.GoldenPathRepo,
	reason string,
	message string,
	clearPR bool,
) error {
	return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
		if clearPR {
			latest.Status.RemediationPR = nil
		}
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionRemediationPR,
			Status:  metav1.ConditionFalse,
			Reason:  reason,
			Message: message,
		})
	})
}

func clearRemediationPRStatus(
	ctx context.Context,
	c client.Client,
	repo *repavev1beta1.GoldenPathRepo,
	reason string,
	message string,
) error {
	if repo.Status.RemediationPR == nil &&
		!status.HasConditionType(repo.Status.Conditions, status.ConditionRemediationPR) {
		return nil
	}
	return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
		latest.Status.RemediationPR = nil
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionRemediationPR,
			Status:  metav1.ConditionFalse,
			Reason:  reason,
			Message: message,
		})
	})
}

func handleGoldenPathRepoDeletion(
	ctx context.Context,
	c client.Client,
	repo *repavev1beta1.GoldenPathRepo,
) (bool, error) {
	if repo.DeletionTimestamp == nil {
		return false, nil
	}
	if !controllerutil.ContainsFinalizer(repo, goldenPathRepoFinalizer) {
		return false, nil
	}
	base := client.MergeFrom(repo.DeepCopy())
	controllerutil.RemoveFinalizer(repo, goldenPathRepoFinalizer)
	if err := c.Patch(ctx, repo, base); err != nil {
		return false, err
	}
	return true, nil
}
