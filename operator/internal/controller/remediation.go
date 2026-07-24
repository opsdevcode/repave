package controller

import (
	"context"
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/git"
	"github.com/opsdevcode/repave/operator/internal/github"
	"github.com/opsdevcode/repave/operator/internal/remediation"
	"github.com/opsdevcode/repave/operator/internal/repave"
	"github.com/opsdevcode/repave/operator/internal/status"
)

const goldenPathRepoFinalizer = "repave.dev/goldenpathrepo-finalizer"

func ensureRemediationFinalizer(
	ctx context.Context,
	c client.Client,
	repo *repavev1alpha1.GoldenPathRepo,
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
	repo *repavev1alpha1.GoldenPathRepo,
	applier repave.ApplyUpgrader,
	gh github.Client,
	repaveCfg repave.Config,
	githubToken string,
) error {
	if !repo.Spec.Remediation.Enabled {
		return clearRemediationPRStatus(ctx, c, repo, status.ReasonRemediationDisabled, "remediation disabled")
	}

	if repo.Status.Phase != repavev1alpha1.GoldenPathRepoPhaseOutOfDate {
		return clearRemediationPRStatus(ctx, c, repo, status.ReasonRemediationCleared, "pins aligned; remediation not required")
	}

	if !meta.IsStatusConditionTrue(repo.Status.Conditions, status.ConditionUpgradePlanned) {
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationPending,
				Message: "waiting for upgrade plan before opening remediation PR",
			})
		})
	}

	if repo.Spec.LocalPath == "" {
		msg := "remediation requires spec.localPath until remote inventory is supported"
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationSkipped,
				Message: msg,
			})
		})
	}

	desiredVersion := repo.Spec.DesiredPins.BlueprintVersion
	if repo.Status.RemediationPR != nil &&
		repo.Status.RemediationPR.DesiredBlueprintVersion == desiredVersion &&
		(repo.Status.RemediationPR.State == remediation.PRStateOpen ||
			repo.Status.RemediationPR.State == remediation.PRStatePlanned) {
		return nil
	}

	if applier == nil {
		applier = repave.CLIApplyUpgrader{}
	}

	branch := remediation.UpgradeBranchName(
		repo.Spec.Remediation.BranchPrefix,
		repo.Spec.DesiredPins.BlueprintName,
		desiredVersion,
	)
	title := remediation.PullRequestTitle(repo.Spec.DesiredPins.BlueprintName, desiredVersion)
	summary := ""
	if repo.Status.UpgradePlan != nil {
		summary = repo.Status.UpgradePlan.Summary
	}
	body := remediation.PullRequestBody(
		summary,
		repo.Spec.DesiredPins.BlueprintName,
		desiredVersion,
		repo.Spec.DesiredPins.StandardVersion,
	)
	commitMessage := title

	applyResult, err := applier.ApplyUpgrade(
		ctx,
		repaveCfg,
		repo.Spec.LocalPath,
		repo.Spec.DesiredPins.BlueprintName,
		branch,
		commitMessage,
	)
	if err != nil {
		msg := err.Error()
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			latest.Status.RemediationPR = nil
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationFailed,
				Message: msg,
			})
		})
	}

	if repo.Spec.Remediation.DryRun {
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			latest.Status.RemediationPR = &repavev1alpha1.RemediationPRStatus{
				Branch:                  applyResult.GitBranch,
				Title:                   title,
				State:                   remediation.PRStatePlanned,
				DesiredBlueprintVersion: desiredVersion,
			}
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionTrue,
				Reason:  status.ReasonRemediationPlanned,
				Message: fmt.Sprintf("dry-run remediation on branch %s", applyResult.GitBranch),
			})
		})
	}

	if repo.Spec.RepoURL == "" {
		msg := "remediation PR requires spec.repoURL when dryRun is false"
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationSkipped,
				Message: msg,
			})
		})
	}

	if githubToken == "" {
		msg := "set GITHUB_TOKEN to push branch and open remediation PR"
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationPending,
				Message: msg,
			})
		})
	}

	if gh == nil {
		gh = &github.HTTPClient{Token: githubToken}
	}

	if err := git.PushBranch(ctx, repo.Spec.LocalPath, repo.Spec.RepoURL, applyResult.GitBranch, githubToken); err != nil {
		msg := err.Error()
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			latest.Status.RemediationPR = nil
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationFailed,
				Message: msg,
			})
		})
	}

	repository, err := github.ParseRepositoryURL(repo.Spec.RepoURL)
	if err != nil {
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationFailed,
				Message: err.Error(),
			})
		})
	}

	pr, err := gh.CreatePullRequest(ctx, github.CreatePullRequestRequest{
		Repository: repository,
		Title:        title,
		Body:         body,
		HeadBranch:   applyResult.GitBranch,
		BaseBranch:   remediation.BaseBranch(repo.Spec.Remediation.BaseBranch),
	})
	if err != nil {
		msg := err.Error()
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
			latest.Status.RemediationPR = nil
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationFailed,
				Message: msg,
			})
		})
	}

	return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
		latest.Status.RemediationPR = &repavev1alpha1.RemediationPRStatus{
			URL:                     pr.HTMLURL,
			Number:                  pr.Number,
			Branch:                  applyResult.GitBranch,
			Title:                   pr.Title,
			State:                   remediation.PRStateOpen,
			DesiredBlueprintVersion: desiredVersion,
		}
		status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
			Type:    status.ConditionRemediationPR,
			Status:  metav1.ConditionTrue,
			Reason:  status.ReasonRemediationPROpen,
			Message: pr.HTMLURL,
		})
	})
}

func clearRemediationPRStatus(
	ctx context.Context,
	c client.Client,
	repo *repavev1alpha1.GoldenPathRepo,
	reason string,
	message string,
) error {
	if repo.Status.RemediationPR == nil &&
		!hasConditionType(repo.Status.Conditions, status.ConditionRemediationPR) {
		return nil
	}
	return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1alpha1.GoldenPathRepo) {
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
	repo *repavev1alpha1.GoldenPathRepo,
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
