package remediation

import (
	"context"
	"testing"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/github"
	"github.com/opsdevcode/repave/operator/internal/inventory"
	"github.com/opsdevcode/repave/operator/internal/repave"
)

func TestWorkDir(t *testing.T) {
	t.Parallel()

	spec := repavev1beta1.GoldenPathRepoSpec{LocalPath: "/tmp/local"}
	got, err := WorkDir(spec, nil)
	if err != nil {
		t.Fatalf("WorkDir(local): %v", err)
	}
	if got != "/tmp/local" {
		t.Fatalf("WorkDir(local) = %q, want /tmp/local", got)
	}

	workspace := &inventory.Workspace{Path: "/tmp/clone"}
	got, err = WorkDir(repavev1beta1.GoldenPathRepoSpec{RepoURL: "https://example.com/a/b"}, workspace)
	if err != nil {
		t.Fatalf("WorkDir(clone): %v", err)
	}
	if got != "/tmp/clone" {
		t.Fatalf("WorkDir(clone) = %q, want /tmp/clone", got)
	}

	if _, err := WorkDir(repavev1beta1.GoldenPathRepoSpec{}, nil); err == nil {
		t.Fatal("WorkDir(empty) expected error")
	}
}

func TestPROpen(t *testing.T) {
	t.Parallel()

	open := &repavev1beta1.RemediationPRStatus{
		State:                   PRStateOpen,
		DesiredBlueprintVersion: "1.0.0",
	}
	if !PROpen(open, "1.0.0") {
		t.Fatal("PROpen(open same version) = false, want true")
	}
	if PROpen(open, "2.0.0") {
		t.Fatal("PROpen(open different version) = true, want false")
	}
	if PROpen(nil, "1.0.0") {
		t.Fatal("PROpen(nil) = true, want false")
	}

	merged := &repavev1beta1.RemediationPRStatus{
		State:                   PRStateMerged,
		DesiredBlueprintVersion: "1.0.0",
	}
	if !PROpen(merged, "1.0.0") {
		t.Fatal("PROpen(merged same version) = false, want true")
	}
}

func TestBuildPRMetadata(t *testing.T) {
	t.Parallel()

	meta := BuildPRMetadata(
		repavev1beta1.RemediationSpec{BranchPrefix: "repave/upgrade"},
		drift.PinSet{BlueprintName: "mod", BlueprintVersion: "1.2.3", StandardVersion: "4.5.6"},
		"diff summary",
	)
	if meta.Branch != "repave/upgrade/mod-1.2.3" {
		t.Fatalf("Branch = %q", meta.Branch)
	}
	if meta.Title == "" || meta.Body == "" || meta.CommitMessage != meta.Title {
		t.Fatalf("unexpected metadata: %+v", meta)
	}
}

func TestPublishPullRequestMergesWhenAllowed(t *testing.T) {
	t.Parallel()

	recorder := &github.RecordingClient{}
	published, err := PublishPullRequest(context.Background(), PublishInput{
		Spec: repavev1beta1.GoldenPathRepoSpec{
			RepoURL: "https://github.com/acme/mod",
		},
		WorkDir: t.TempDir(),
		Metadata: PRMetadata{
			Title: "chore(repave): upgrade mod to 1.2.3",
		},
		ApplyResult: repave.ApplyResult{
			GitBranch: "repave/upgrade/mod-1.2.3",
			Pushed:    true,
			AutoMerge: &repave.AutoMergeDecision{Allowed: true, Reason: "mechanical"},
		},
		GitHubToken: "token",
		PRClient:    recorder,
	})
	if err != nil {
		t.Fatalf("PublishPullRequest: %v", err)
	}
	if recorder.MergeCalls != 1 {
		t.Fatalf("MergeCalls = %d, want 1", recorder.MergeCalls)
	}
	if !published.Merged || published.MergeCommitSHA == "" {
		t.Fatalf("published = %+v, want merged with sha", published)
	}
}

func TestPublishPullRequestSkipsMergeWhenReviewRequired(t *testing.T) {
	t.Parallel()

	recorder := &github.RecordingClient{}
	published, err := PublishPullRequest(context.Background(), PublishInput{
		Spec: repavev1beta1.GoldenPathRepoSpec{
			RepoURL: "https://github.com/acme/mod",
		},
		WorkDir: t.TempDir(),
		Metadata: PRMetadata{
			Title: "chore(repave): upgrade mod to 1.2.3",
		},
		ApplyResult: repave.ApplyResult{
			GitBranch: "repave/upgrade/mod-1.2.3",
			Pushed:    true,
			AutoMerge: &repave.AutoMergeDecision{Allowed: false, Reason: "kill_switch"},
		},
		GitHubToken: "token",
		PRClient:    recorder,
	})
	if err != nil {
		t.Fatalf("PublishPullRequest: %v", err)
	}
	if recorder.MergeCalls != 0 {
		t.Fatalf("MergeCalls = %d, want 0", recorder.MergeCalls)
	}
	if published.Merged {
		t.Fatal("expected review-required PR to stay unmerged")
	}
}
