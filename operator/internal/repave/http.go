package repave

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

const (
	v2PlanPath         = "/api/v2/upgrades/plan"
	v2ApplyPath        = "/api/v2/upgrades/apply"
	upgradeHTTPTimeout = 30 * time.Second
)

func defaultUpgradeHTTPClient() *http.Client {
	return &http.Client{Timeout: upgradeHTTPTimeout}
}

// HTTPPlanUpgrader calls POST /api/v2/upgrades/plan.
type HTTPPlanUpgrader struct {
	BaseURL    string
	HTTPClient *http.Client
}

func (h HTTPPlanUpgrader) client() *http.Client {
	if h.HTTPClient != nil {
		return h.HTTPClient
	}
	return defaultUpgradeHTTPClient()
}

func (h HTTPPlanUpgrader) PlanUpgrade(
	ctx context.Context,
	_ Config,
	targetRepo string,
	blueprintName string,
) (PlanResult, error) {
	body := upgradePlanBody(targetRepo, blueprintName)
	var result PlanResult
	if err := h.postJSON(ctx, v2PlanPath, body, &result); err != nil {
		return PlanResult{}, err
	}
	return result, nil
}

// HTTPApplyUpgrader calls POST /api/v2/upgrades/apply.
type HTTPApplyUpgrader struct {
	BaseURL    string
	HTTPClient *http.Client
}

func (h HTTPApplyUpgrader) client() *http.Client {
	if h.HTTPClient != nil {
		return h.HTTPClient
	}
	return defaultUpgradeHTTPClient()
}

func (h HTTPApplyUpgrader) ApplyUpgrade(
	ctx context.Context,
	_ Config,
	targetRepo string,
	blueprintName string,
	gitBranch string,
	commitMessage string,
	preserveLocal bool,
	pushRemote bool,
) (ApplyResult, error) {
	body := upgradeApplyBody(
		targetRepo,
		blueprintName,
		gitBranch,
		commitMessage,
		preserveLocal,
		pushRemote,
	)
	var result ApplyResult
	if err := h.postJSON(ctx, v2ApplyPath, body, &result); err != nil {
		return ApplyResult{}, err
	}
	return result, nil
}

func (h HTTPPlanUpgrader) postJSON(ctx context.Context, path string, body any, dest any) error {
	return postUpgradeJSON(ctx, h.client(), h.BaseURL, path, body, dest)
}

func (h HTTPApplyUpgrader) postJSON(ctx context.Context, path string, body any, dest any) error {
	return postUpgradeJSON(ctx, h.client(), h.BaseURL, path, body, dest)
}

func postUpgradeJSON(
	ctx context.Context,
	client *http.Client,
	baseURL string,
	path string,
	body any,
	dest any,
) error {
	base := strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if base == "" {
		return fmt.Errorf("repave API URL is not configured; set REPAVE_API_URL")
	}
	payload, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("encode upgrade request: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, base+path, bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("build upgrade request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if token := strings.TrimSpace(apiTokenFromEnv()); token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("repave API %s: %w", path, err)
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read upgrade response: %w", err)
	}
	if resp.StatusCode >= 300 {
		return fmt.Errorf("repave API %s: %s", path, extractHTTPError(raw, resp.StatusCode))
	}
	if err := json.Unmarshal(raw, dest); err != nil {
		return fmt.Errorf("parse upgrade json: %w", err)
	}
	return nil
}

func upgradePlanBody(targetRepo, blueprintName string) map[string]any {
	body := map[string]any{}
	if isHTTPRemote(targetRepo) {
		body["repo_url"] = strings.TrimSpace(targetRepo)
	} else {
		body["target_repo"] = strings.TrimSpace(targetRepo)
	}
	if strings.TrimSpace(blueprintName) != "" {
		body["blueprint"] = strings.TrimSpace(blueprintName)
	}
	return body
}

func upgradeApplyBody(
	targetRepo string,
	blueprintName string,
	gitBranch string,
	commitMessage string,
	preserveLocal bool,
	pushRemote bool,
) map[string]any {
	body := upgradePlanBody(targetRepo, blueprintName)
	body["git_branch"] = strings.TrimSpace(gitBranch)
	body["commit_message"] = strings.TrimSpace(commitMessage)
	if preserveLocal {
		body["preserve_local"] = true
	}
	if pushRemote {
		body["push"] = true
	}
	return body
}

func isHTTPRemote(value string) bool {
	lower := strings.ToLower(strings.TrimSpace(value))
	return strings.HasPrefix(lower, "http://") || strings.HasPrefix(lower, "https://")
}

func extractHTTPError(raw []byte, status int) string {
	var payload struct {
		Detail any `json:"detail"`
	}
	if err := json.Unmarshal(raw, &payload); err == nil && payload.Detail != nil {
		switch typed := payload.Detail.(type) {
		case string:
			if strings.TrimSpace(typed) != "" {
				return typed
			}
		}
	}
	text := strings.TrimSpace(string(raw))
	if text == "" {
		return fmt.Sprintf("HTTP %d", status)
	}
	return text
}

func apiTokenFromEnv() string {
	return strings.TrimSpace(os.Getenv("REPAVE_API_TOKEN"))
}
