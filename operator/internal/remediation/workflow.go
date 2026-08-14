package remediation

import (
	"context"
	"errors"
	"fmt"
	"strings"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/conventions"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/git"
	"github.com/opsdevcode/repave/operator/internal/github"
	"github.com/opsdevcode/repave/operator/internal/inventory"
	"github.com/opsdevcode/repave/operator/internal/repave"
)

// WorkDir resolves the filesystem path for remediation apply and push.
func WorkDir(
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

// PROpen reports whether status already tracks a PR for desiredVersion
// (open, planned, or merged — do not re-apply).
func PROpen(existing *repavev1beta1.RemediationPRStatus, desiredVersion string) bool {
	if existing == nil {
		return false
	}
	if existing.DesiredBlueprintVersion != desiredVersion {
		return false
	}
	return existing.State == PRStateOpen ||
		existing.State == PRStatePlanned ||
		existing.State == PRStateMerged
}

// PRMetadata holds branch, title, body, and commit message for a remediation PR.
type PRMetadata struct {
	Branch        string
	Title         string
	Body          string
	CommitMessage string
	Labels        []string
}

// BuildPRMetadata constructs deterministic PR fields from remediation spec and desired pins.
func BuildPRMetadata(
	spec repavev1beta1.RemediationSpec,
	desired drift.PinSet,
	upgradePlanSummary string,
) PRMetadata {
	defaults := conventions.LoadPullRequestDefaults()
	prefix := strings.TrimSpace(spec.BranchPrefix)
	if prefix == "" {
		prefix = defaults.BranchPrefixUpgrade
	}
	branch := UpgradeBranchName(prefix, desired.BlueprintName, desired.BlueprintVersion)
	title := conventions.UpgradeTitle(desired.BlueprintName, desired.BlueprintVersion)
	body := conventions.UpgradeBody(
		upgradePlanSummary,
		desired.BlueprintName,
		desired.BlueprintVersion,
		desired.StandardVersion,
		"",
	)
	return PRMetadata{
		Branch:        branch,
		Title:         title,
		Body:          body,
		CommitMessage: title,
		Labels:        defaults.Labels,
	}
}

// ApplyInput drives apply-upgrade for remediation.
type ApplyInput struct {
	Spec      repavev1beta1.GoldenPathRepoSpec
	WorkDir   string
	Desired   drift.PinSet
	Metadata  PRMetadata
	Applier   repave.ApplyUpgrader
	RepaveCfg repave.Config
}

// ApplyUpgradeChanges runs apply-upgrade against the remediation work tree.
func ApplyUpgradeChanges(ctx context.Context, in ApplyInput) (repave.ApplyResult, error) {
	pushRemote := in.RepaveCfg.HTTPMode() && in.Spec.RepoURL != "" && !in.Spec.Remediation.DryRun
	applyTarget := repave.UpgradeTarget(in.Spec.RepoURL, in.Spec.LocalPath, in.WorkDir, in.RepaveCfg)
	return in.Applier.ApplyUpgrade(
		ctx,
		in.RepaveCfg,
		applyTarget,
		in.Desired.BlueprintName,
		in.Metadata.Branch,
		in.Metadata.CommitMessage,
		in.Spec.Remediation.PreserveLocal,
		pushRemote,
	)
}

// PublishInput drives branch push and GitHub PR creation after apply-upgrade.
type PublishInput struct {
	Spec           repavev1beta1.GoldenPathRepoSpec
	WorkDir        string
	Metadata       PRMetadata
	ApplyResult    repave.ApplyResult
	DesiredVersion string
	GitHubToken    string
	PRClient       github.Client
}

// PublishedPR is the opened (and optionally merged) remediation pull request.
type PublishedPR struct {
	URL            string
	Number         int
	Title          string
	Branch         string
	Merged         bool
	MergeCommitSHA string
	MergeError     string
}

// PublishPullRequest pushes the remediation branch when needed and opens a GitHub PR.
func PublishPullRequest(ctx context.Context, in PublishInput) (PublishedPR, error) {
	if in.Spec.RepoURL == "" {
		return PublishedPR{}, ErrRepoURLRequired
	}

	resolvedToken, err := github.ResolveAccessToken(in.GitHubToken)
	if err != nil {
		return PublishedPR{}, err
	}
	if resolvedToken == "" {
		return PublishedPR{}, ErrGitHubTokenRequired
	}

	prClient := in.PRClient
	if prClient == nil {
		prClient = &github.HTTPClient{Token: resolvedToken}
	}

	if !in.ApplyResult.Pushed {
		if err := git.PushBranch(ctx, in.WorkDir, in.Spec.RepoURL, in.ApplyResult.GitBranch, resolvedToken); err != nil {
			return PublishedPR{}, err
		}
	}

	repository, err := github.ParseRepositoryURL(in.Spec.RepoURL)
	if err != nil {
		return PublishedPR{}, err
	}

	pr, err := prClient.CreatePullRequest(ctx, github.CreatePullRequestRequest{
		Repository: repository,
		Title:      in.Metadata.Title,
		Body:       in.Metadata.Body,
		HeadBranch: in.ApplyResult.GitBranch,
		BaseBranch: BaseBranch(in.Spec.Remediation.BaseBranch),
		Labels:     in.Metadata.Labels,
	})
	if err != nil {
		return PublishedPR{}, err
	}

	published := PublishedPR{
		URL:    pr.HTMLURL,
		Number: pr.Number,
		Title:  pr.Title,
		Branch: in.ApplyResult.GitBranch,
	}
	if in.ApplyResult.AutoMerge == nil || !in.ApplyResult.AutoMerge.Allowed {
		return published, nil
	}

	merged, err := prClient.MergePullRequest(ctx, github.MergePullRequestRequest{
		Repository:  repository,
		Number:      pr.Number,
		CommitTitle: in.Metadata.Title,
	})
	if err != nil {
		published.MergeError = err.Error()
		return published, nil
	}
	published.Merged = merged.Merged
	published.MergeCommitSHA = merged.SHA
	return published, nil
}

// ErrGitHubTokenRequired is returned when GitHub credentials are missing for PR publish.
var ErrGitHubTokenRequired = errors.New(
	"set GITHUB_TOKEN or GitHub App credentials to push branch and open remediation PR",
)

// ErrRepoURLRequired is returned when remediation publish needs spec.repoURL.
var ErrRepoURLRequired = errors.New("remediation PR requires spec.repoURL when dryRun is false")
