package github

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// HTTPClient calls the GitHub REST API with a personal access token.
type HTTPClient struct {
	Token      string
	HTTPClient *http.Client
	// BaseURL overrides the GitHub API host (tests only).
	BaseURL string
}

func (c *HTTPClient) baseURL() string {
	if strings.TrimSpace(c.BaseURL) != "" {
		return strings.TrimRight(strings.TrimSpace(c.BaseURL), "/")
	}
	return "https://api.github.com"
}

func (c *HTTPClient) client() *http.Client {
	if c.HTTPClient != nil {
		return c.HTTPClient
	}
	return &http.Client{Timeout: 30 * time.Second}
}

type pullRequestPayload struct {
	Title string `json:"title"`
	Body  string `json:"body"`
	Head  string `json:"head"`
	Base  string `json:"base"`
}

type pullRequestResponse struct {
	Number  int    `json:"number"`
	HTMLURL string `json:"html_url"`
	Title   string `json:"title"`
	State   string `json:"state"`
}

func (c *HTTPClient) CreatePullRequest(
	ctx context.Context,
	req CreatePullRequestRequest,
) (PullRequest, error) {
	token := strings.TrimSpace(c.Token)
	if token == "" {
		return PullRequest{}, fmt.Errorf("GitHub token is not configured")
	}

	payload, err := json.Marshal(pullRequestPayload{
		Title: req.Title,
		Body:  req.Body,
		Head:  req.HeadBranch,
		Base:  req.BaseBranch,
	})
	if err != nil {
		return PullRequest{}, fmt.Errorf("marshal pull request: %w", err)
	}

	url := fmt.Sprintf(
		"%s/repos/%s/%s/pulls",
		c.baseURL(),
		req.Repository.Owner,
		req.Repository.Name,
	)
	resp, body, err := c.doGitHub(ctx, http.MethodPost, url, payload, token)
	if err != nil {
		return PullRequest{}, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return PullRequest{}, fmt.Errorf("GitHub API %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var parsed pullRequestResponse
	if err := json.Unmarshal(body, &parsed); err != nil {
		return PullRequest{}, fmt.Errorf("decode pull request response: %w", err)
	}
	if len(req.Labels) > 0 && parsed.Number > 0 {
		if err := c.addIssueLabels(ctx, req.Repository, parsed.Number, req.Labels, token); err != nil {
			return PullRequest{}, err
		}
	}
	return PullRequest{
		Number:  parsed.Number,
		HTMLURL: parsed.HTMLURL,
		Title:   parsed.Title,
		State:   parsed.State,
	}, nil
}

func (c *HTTPClient) addIssueLabels(
	ctx context.Context,
	repository Repository,
	pullNumber int,
	labels []string,
	token string,
) error {
	if len(labels) == 0 {
		return nil
	}
	payload, err := json.Marshal(map[string]any{"labels": labels})
	if err != nil {
		return fmt.Errorf("marshal labels: %w", err)
	}
	url := fmt.Sprintf(
		"%s/repos/%s/%s/issues/%d/labels",
		c.baseURL(),
		repository.Owner,
		repository.Name,
		pullNumber,
	)
	resp, body, err := c.doGitHub(ctx, http.MethodPost, url, payload, token)
	if err != nil {
		return err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("GitHub label API %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	return nil
}
