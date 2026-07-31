package controller

import (
	"context"
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/git"
	"github.com/opsdevcode/repave/operator/internal/github"
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
	gh github.Client,
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

	workDir, workErr := remediationWorkDir(repo.Spec, workspace)
	if workErr != nil {
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationSkipped,
				Message: workErr.Error(),
			})
		})
	}

	desiredVersion := desired.BlueprintVersion
	if repo.Status.RemediationPR != nil &&
		repo.Status.RemediationPR.DesiredBlueprintVersion == desiredVersion &&
		(repo.Status.RemediationPR.State == remediation.PRStateOpen ||
			repo.Status.RemediationPR.State == remediation.PRStatePlanned) {
		return nil
	}

	if applier == nil {
		applier = repave.NewApplyUpgrader(repaveCfg)
	}

	branch := remediation.UpgradeBranchName(
		repo.Spec.Remediation.BranchPrefix,
		desired.BlueprintName,
		desiredVersion,
	)
	title := remediation.PullRequestTitle(desired.BlueprintName, desiredVersion)
	summary := ""
	if repo.Status.UpgradePlan != nil {
		summary = repo.Status.UpgradePlan.Summary
	}
	body := remediation.PullRequestBody(
		summary,
		desired.BlueprintName,
		desiredVersion,
		desired.StandardVersion,
	)
	commitMessage := title

	pushRemote := repaveCfg.HTTPMode() && repo.Spec.RepoURL != "" && !repo.Spec.Remediation.DryRun
	applyTarget := repave.UpgradeTarget(repo.Spec.RepoURL, repo.Spec.LocalPath, workDir, repaveCfg)

	applyResult, err := applier.ApplyUpgrade(
		ctx,
		repaveCfg,
		applyTarget,
		desired.BlueprintName,
		branch,
		commitMessage,
		repo.Spec.Remediation.PreserveLocal,
		pushRemote,
	)
	if err != nil {
		msg := err.Error()
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
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
		err := patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
			latest.Status.RemediationPR = &repavev1beta1.RemediationPRStatus{
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
		if err != nil {
			return err
		}
		sendOperatorNotify(notify.EventRemediationPRPlanned, repo, applyResult.GitBranch, "", title,
			fmt.Sprintf("dry-run remediation on branch %s", applyResult.GitBranch))
		return nil
	}

	if repo.Spec.RepoURL == "" {
		msg := "remediation PR requires spec.repoURL when dryRun is false"
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationSkipped,
				Message: msg,
			})
		})
	}

	resolvedToken, resolveErr := github.ResolveAccessToken("")
	if resolveErr != nil {
		msg := resolveErr.Error()
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationFailed,
				Message: msg,
			})
		})
	}
	if resolvedToken == "" {
		msg := "set GITHUB_TOKEN or GitHub App credentials to push branch and open remediation PR"
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationPending,
				Message: msg,
			})
		})
	}
	githubToken = resolvedToken
	gh = &github.HTTPClient{Token: githubToken}

	if !applyResult.Pushed {
		if err := git.PushBranch(ctx, workDir, repo.Spec.RepoURL, applyResult.GitBranch, githubToken); err != nil {
			msg := err.Error()
			return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
				latest.Status.RemediationPR = nil
				status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
					Type:    status.ConditionRemediationPR,
					Status:  metav1.ConditionFalse,
					Reason:  status.ReasonRemediationFailed,
					Message: msg,
				})
			})
		}
	}

	repository, err := github.ParseRepositoryURL(repo.Spec.RepoURL)
	if err != nil {
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
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
		return patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
			latest.Status.RemediationPR = nil
			status.SetGoldenPathRepoCondition(&latest.Status.Conditions, metav1.Condition{
				Type:    status.ConditionRemediationPR,
				Status:  metav1.ConditionFalse,
				Reason:  status.ReasonRemediationFailed,
				Message: msg,
			})
		})
	}

	if err := patchGoldenPathRepoStatus(ctx, c, repo, func(latest *repavev1beta1.GoldenPathRepo) {
		latest.Status.RemediationPR = &repavev1beta1.RemediationPRStatus{
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
	}); err != nil {
		return err
	}
	sendOperatorNotify(notify.EventRemediationPROpened, repo, applyResult.GitBranch, pr.HTMLURL, pr.Title,
		fmt.Sprintf("Remediation PR opened: %s", pr.Title))
	return nil
}

func remediationWorkDir(
	spec repavev1beta1.GoldenPathRepoSpec,
	workspace *inventory.Workspace,
) (string, error) {
	if spec.LocalPath != "" {
		return spec.LocalPath, nil
	}
	if workspace != nil && workspace.Path != "" {
		return workspace.Path, nil
	}
	return "", fmt.Errorf("remediation requires spec.localPath or a materialized spec.repoURL clone")
}

func sendOperatorNotify(
	event string,
	repo *repavev1beta1.GoldenPathRepo,
	branch string,
	prURL string,
	_ string,
	message string,
) {
	repository := repo.Spec.RepoURL
	if repository == "" {
		repository = repo.Spec.LocalPath
	}
	cfg := notify.LoadConfig()
	notify.Send(cfg, event, notify.Payload{
		Namespace:  repo.Namespace,
		Name:       repo.Name,
		Repository: repository,
		Message:    message,
		PRURL:      prURL,
		Branch:     branch,
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
		!hasConditionType(repo.Status.Conditions, status.ConditionRemediationPR) {
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
