package github

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// HTTPClient calls the GitHub REST API with a personal access token.
type HTTPClient struct {
	Token      string
	HTTPClient *http.Client
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
	Number int    `json:"number"`
	HTMLURL string `json:"html_url"`
	Title  string `json:"title"`
	State  string `json:"state"`
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
		return PullRequest{}, err
	}

	url := fmt.Sprintf(
		"https://api.github.com/repos/%s/%s/pulls",
		req.Repository.Owner,
		req.Repository.Name,
	)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(payload))
	if err != nil {
		return PullRequest{}, err
	}
	httpReq.Header.Set("Authorization", "Bearer "+token)
	httpReq.Header.Set("Accept", "application/vnd.github+json")
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.client().Do(httpReq)
	if err != nil {
		return PullRequest{}, err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return PullRequest{}, fmt.Errorf("GitHub API %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var parsed pullRequestResponse
	if err := json.Unmarshal(body, &parsed); err != nil {
		return PullRequest{}, err
	}
	return PullRequest{
		Number:  parsed.Number,
		HTMLURL: parsed.HTMLURL,
		Title:   parsed.Title,
		State:   parsed.State,
	}, nil
}
