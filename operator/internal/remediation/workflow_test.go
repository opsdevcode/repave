package remediation

import (
	"testing"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/inventory"
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
