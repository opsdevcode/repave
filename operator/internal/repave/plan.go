package repave

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
)

const defaultCLI = "repave"

// Config locates the repave engine checkout and CLI binary for plan-upgrade.
type Config struct {
	RepoRoot string
	Command  string
}

// PlanResult is the JSON payload from `repave plan-upgrade --format json`.
type PlanResult struct {
	BlueprintName    string   `json:"blueprint_name"`
	BlueprintVersion string   `json:"blueprint_version"`
	ChangedFileCount int      `json:"changed_file_count"`
	Added            []string `json:"added"`
	Modified         []string `json:"modified"`
	Removed          []string `json:"removed"`
	Summary          string   `json:"summary"`
}

// PlanUpgrader computes upgrade diffs via the repave CLI.
type PlanUpgrader interface {
	PlanUpgrade(
		ctx context.Context,
		cfg Config,
		targetRepo string,
		blueprintName string,
	) (PlanResult, error)
}

// CLIPlanUpgrader invokes `repave plan-upgrade`.
type CLIPlanUpgrader struct{}

func (CLIPlanUpgrader) PlanUpgrade(
	ctx context.Context,
	cfg Config,
	targetRepo string,
	blueprintName string,
) (PlanResult, error) {
	if strings.TrimSpace(cfg.RepoRoot) == "" {
		return PlanResult{}, fmt.Errorf("repave repo root is not configured")
	}
	command := strings.TrimSpace(cfg.Command)
	if command == "" {
		command = defaultCLI
	}

	args := []string{
		"plan-upgrade",
		"--repo-root", cfg.RepoRoot,
		"--target-repo", targetRepo,
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
		return PlanResult{}, fmt.Errorf("repave plan-upgrade: %s", msg)
	}

	var result PlanResult
	if err := json.Unmarshal(stdout.Bytes(), &result); err != nil {
		return PlanResult{}, fmt.Errorf("parse plan-upgrade json: %w", err)
	}
	return result, nil
}

// ConfigFromEnv reads REPAVE_REPO_ROOT and optional REPAVE_CLI.
func ConfigFromEnv(repoRootEnv, cliEnv string) Config {
	return Config{
		RepoRoot: strings.TrimSpace(repoRootEnv),
		Command:  strings.TrimSpace(cliEnv),
	}
}

// StaticPlanUpgrader returns a fixed result (envtest and unit tests).
type StaticPlanUpgrader struct {
	Result PlanResult
	Err    error
	Calls  int
}

func (s *StaticPlanUpgrader) PlanUpgrade(
	_ context.Context,
	_ Config,
	_ string,
	_ string,
) (PlanResult, error) {
	s.Calls++
	if s.Err != nil {
		return PlanResult{}, s.Err
	}
	return s.Result, nil
}
