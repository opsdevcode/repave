package repave

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
)

// ApplyResult is the JSON payload from `repave apply-upgrade --format json`.
type ApplyResult struct {
	BlueprintName    string `json:"blueprint_name"`
	BlueprintVersion string `json:"blueprint_version"`
	ChangedFileCount int    `json:"changed_file_count"`
	GitBranch        string `json:"git_branch"`
	CommitSHA        string `json:"commit_sha"`
	Summary          string `json:"summary"`
}

// ApplyUpgrader applies rendered upgrades onto a local git checkout.
type ApplyUpgrader interface {
	ApplyUpgrade(
		ctx context.Context,
		cfg Config,
		targetRepo string,
		blueprintName string,
		gitBranch string,
		commitMessage string,
	) (ApplyResult, error)
}

// CLIApplyUpgrader invokes `repave apply-upgrade`.
type CLIApplyUpgrader struct{}

func (CLIApplyUpgrader) ApplyUpgrade(
	ctx context.Context,
	cfg Config,
	targetRepo string,
	blueprintName string,
	gitBranch string,
	commitMessage string,
) (ApplyResult, error) {
	if strings.TrimSpace(cfg.RepoRoot) == "" {
		return ApplyResult{}, fmt.Errorf("repave repo root is not configured")
	}
	command := strings.TrimSpace(cfg.Command)
	if command == "" {
		command = defaultCLI
	}

	args := []string{
		"apply-upgrade",
		"--repo-root", cfg.RepoRoot,
		"--target-repo", targetRepo,
		"--git-branch", gitBranch,
		"--commit-message", commitMessage,
		"--format", "json",
	}
	if blueprintName != "" {
		args = append(args, "--blueprint", blueprintName)
	}

	cmd := exec.CommandContext(ctx, command, args...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		msg := strings.TrimSpace(stderr.String())
		if msg == "" {
			msg = err.Error()
		}
		return ApplyResult{}, fmt.Errorf("repave apply-upgrade: %s", msg)
	}

	var result ApplyResult
	if err := json.Unmarshal(stdout.Bytes(), &result); err != nil {
		return ApplyResult{}, fmt.Errorf("parse apply-upgrade json: %w", err)
	}
	return result, nil
}

// StaticApplyUpgrader returns a fixed apply result (envtest and unit tests).
type StaticApplyUpgrader struct {
	Result ApplyResult
	Err    error
	Calls  int
}

func (s *StaticApplyUpgrader) ApplyUpgrade(
	_ context.Context,
	_ Config,
	_ string,
	_ string,
	_ string,
	_ string,
) (ApplyResult, error) {
	s.Calls++
	if s.Err != nil {
		return ApplyResult{}, s.Err
	}
	return s.Result, nil
}
