package repave

import (
	"os"
	"strings"
	"time"
)

// Config locates the repave engine for upgrades (CLI checkout or HTTP API).
type Config struct {
	// RepoRoot is the monorepo root for CLI mode (--repo-root).
	RepoRoot string
	// Command is the repave CLI binary for CLI mode.
	Command string
	// APIURL is the portal/API base URL (for example http://repave-portal:8000).
	// When set, plan/apply call /api/v2/upgrades/* instead of exec'ing the CLI.
	APIURL string
}

// HTTPMode reports whether upgrades should use /api/v2 HTTP instead of the CLI.
func (c Config) HTTPMode() bool {
	return strings.TrimSpace(c.APIURL) != ""
}

// RemoteResyncFromEnv reads REPAVE_OPERATOR_REMOTE_RESYNC (Go duration, for example 15m).
// Invalid or unset values return 0 and, when raw was set but invalid, the raw string for logging.
func RemoteResyncFromEnv() (time.Duration, string) {
	raw := strings.TrimSpace(os.Getenv("REPAVE_OPERATOR_REMOTE_RESYNC"))
	if raw == "" {
		return 0, ""
	}
	parsed, err := time.ParseDuration(raw)
	if err != nil || parsed <= 0 {
		return 0, raw
	}
	return parsed, ""
}

// GitHubPATFromEnv reads GITHUB_TOKEN for PAT-based GitHub access.
func GitHubPATFromEnv() string {
	return strings.TrimSpace(os.Getenv("GITHUB_TOKEN"))
}

// ConfigFromEnv reads REPAVE_REPO_ROOT, optional REPAVE_CLI, and REPAVE_API_URL.
func ConfigFromEnv(repoRootEnv, cliEnv, apiURLEnv string) Config {
	apiURL := strings.TrimSpace(apiURLEnv)
	apiURL = strings.TrimRight(apiURL, "/")
	return Config{
		RepoRoot: strings.TrimSpace(repoRootEnv),
		Command:  strings.TrimSpace(cliEnv),
		APIURL:   apiURL,
	}
}

// NewPlanUpgrader selects HTTP or CLI implementation from config.
func NewPlanUpgrader(cfg Config) PlanUpgrader {
	if cfg.HTTPMode() {
		return HTTPPlanUpgrader{BaseURL: cfg.APIURL}
	}
	return CLIPlanUpgrader{}
}

// NewApplyUpgrader selects HTTP or CLI implementation from config.
func NewApplyUpgrader(cfg Config) ApplyUpgrader {
	if cfg.HTTPMode() {
		return HTTPApplyUpgrader{BaseURL: cfg.APIURL}
	}
	return CLIApplyUpgrader{}
}

// UpgradeTarget returns the path or repo URL to pass to plan/apply.
// HTTP mode uses spec.repoURL so the API can clone server-side.
func UpgradeTarget(repoURL, localPath, workspacePath string, cfg Config) string {
	if cfg.HTTPMode() && strings.TrimSpace(repoURL) != "" {
		return strings.TrimSpace(repoURL)
	}
	if strings.TrimSpace(localPath) != "" {
		return strings.TrimSpace(localPath)
	}
	return strings.TrimSpace(workspacePath)
}
