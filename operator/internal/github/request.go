package github

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"time"
)

const githubMaxRetries = 3

func (c *HTTPClient) doGitHub(
	ctx context.Context,
	method string,
	url string,
	payload []byte,
	token string,
) (*http.Response, []byte, error) {
	installationID := CurrentInstallationID()
	minRemaining := MinRemainingFromEnv()
	if err := DefaultRateLimitTracker().WaitIfNeeded(ctx, installationID, minRemaining); err != nil {
		return nil, nil, err
	}

	var lastErr error
	for attempt := 0; attempt <= githubMaxRetries; attempt++ {
		var bodyReader io.Reader
		if len(payload) > 0 {
			bodyReader = bytes.NewReader(payload)
		}
		httpReq, err := http.NewRequestWithContext(ctx, method, url, bodyReader)
		if err != nil {
			return nil, nil, fmt.Errorf("build GitHub request: %w", err)
		}
		httpReq.Header.Set("Authorization", "Bearer "+token)
		httpReq.Header.Set("Accept", "application/vnd.github+json")
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq.Header.Set("X-GitHub-Api-Version", "2022-11-28")

		resp, err := c.client().Do(httpReq)
		if err != nil {
			return nil, nil, fmt.Errorf("GitHub API request: %w", err)
		}

		body, readErr := io.ReadAll(resp.Body)
		resp.Body.Close()
		if readErr != nil {
			return nil, nil, fmt.Errorf("read GitHub response: %w", readErr)
		}

		DefaultRateLimitTracker().UpdateFromHeaders(resp.Header, installationID)

		if resp.StatusCode == http.StatusTooManyRequests && attempt < githubMaxRetries {
			delay := BackoffSeconds(resp.Header.Get("Retry-After"), attempt)
			if delay > 0 {
				timer := time.NewTimer(delay)
				select {
				case <-ctx.Done():
					timer.Stop()
					return nil, nil, ctx.Err()
				case <-timer.C:
				}
			}
			lastErr = fmt.Errorf("GitHub API 429: %s", string(body))
			continue
		}

		return resp, body, nil
	}
	if lastErr != nil {
		return nil, nil, lastErr
	}
	return nil, nil, fmt.Errorf("GitHub API request failed after retries")
}
