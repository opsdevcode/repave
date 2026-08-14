package repave

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCLIApplyUpgraderPassesPreserveLocalFlag(t *testing.T) {
	repoRoot := t.TempDir()
	target := t.TempDir()
	logPath := filepath.Join(t.TempDir(), "invocation.log")

	script := filepath.Join(t.TempDir(), "repave-stub")
	if err := os.WriteFile(
		script,
		[]byte("#!/bin/sh\nprintf '%s\\n' \"$@\" >> \""+logPath+"\"\n"+
			"echo '{\"blueprint_name\":\"terraform-module-generic\",\"blueprint_version\":\"0.9.0\","+
			"\"changed_file_count\":1,\"git_branch\":\"b\",\"commit_sha\":\"c\",\"summary\":\"ok\"}'\n"),
		0o755,
	); err != nil {
		t.Fatal(err)
	}

	applier := CLIApplyUpgrader{}
	_, err := applier.ApplyUpgrade(
		context.Background(),
		Config{RepoRoot: repoRoot, Command: script},
		target,
		"terraform-module-generic",
		"repave/upgrade-test",
		"upgrade",
		true,
		false,
	)
	if err != nil {
		t.Fatalf("ApplyUpgrade: %v", err)
	}

	logged, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(strings.Fields(string(logged)), " ")
	if !strings.Contains(joined, "--preserve-local") {
		t.Fatalf("expected --preserve-local in logged args, got %q", joined)
	}
}

func TestCLIApplyUpgraderParsesAutoMerge(t *testing.T) {
	repoRoot := t.TempDir()
	target := t.TempDir()
	script := filepath.Join(t.TempDir(), "repave-stub")
	if err := os.WriteFile(
		script,
		[]byte("#!/bin/sh\n"+
			"echo '{\"blueprint_name\":\"terraform-module-generic\",\"blueprint_version\":\"0.9.0\","+
			"\"changed_file_count\":1,\"git_branch\":\"b\",\"commit_sha\":\"c\",\"summary\":\"ok\","+
			"\"auto_merge\":{\"allowed\":true,\"reason\":\"mechanical pin bump\"}}'\n"),
		0o755,
	); err != nil {
		t.Fatal(err)
	}

	result, err := CLIApplyUpgrader{}.ApplyUpgrade(
		context.Background(),
		Config{RepoRoot: repoRoot, Command: script},
		target,
		"terraform-module-generic",
		"repave/upgrade-test",
		"upgrade",
		false,
		false,
	)
	if err != nil {
		t.Fatalf("ApplyUpgrade: %v", err)
	}
	if result.AutoMerge == nil || !result.AutoMerge.Allowed {
		t.Fatalf("AutoMerge = %+v, want allowed", result.AutoMerge)
	}
	if result.AutoMerge.Reason != "mechanical pin bump" {
		t.Fatalf("AutoMerge.Reason = %q", result.AutoMerge.Reason)
	}
}
