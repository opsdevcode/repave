package github_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync/atomic"
	"testing"
	"time"

	"github.com/opsdevcode/repave/operator/internal/github"
)

func TestHTTPClientRetriesOn429(t *testing.T) {
	github.ResetRateLimitTracker()
	var calls atomic.Int32
	resetAt := time.Now().Add(time.Minute).Unix()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		count := calls.Add(1)
		w.Header().Set("X-RateLimit-Remaining", "4999")
		w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(resetAt, 10))
		if count == 1 {
			w.Header().Set("Retry-After", "0")
			w.WriteHeader(http.StatusTooManyRequests)
			_, _ = w.Write([]byte(`{"message":"rate limit"}`))
			return
		}
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"number":7,"html_url":"https://github.com/acme/mod/pull/7","title":"t","state":"open"}`))
	}))
	defer srv.Close()

	client := &github.HTTPClient{
		Token:      "token",
		HTTPClient: srv.Client(),
		BaseURL:    srv.URL,
	}
	repo := github.Repository{Owner: "acme", Name: "mod"}
	_, err := client.CreatePullRequest(context.Background(), github.CreatePullRequestRequest{
		Repository: repo,
		Title:      "upgrade",
		Body:       "body",
		HeadBranch: "repave/upgrade",
		BaseBranch: "main",
	})
	if err != nil {
		t.Fatalf("CreatePullRequest: %v", err)
	}
	if calls.Load() < 2 {
		t.Fatalf("expected retry after 429, got %d calls", calls.Load())
	}
}

func TestHTTPClientMergePullRequest(t *testing.T) {
	github.ResetRateLimitTracker()
	var method string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		method = r.Method
		if r.URL.Path != "/repos/acme/mod/pulls/9/merge" {
			t.Fatalf("path = %q", r.URL.Path)
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"sha":"abc123","merged":true}`))
	}))
	defer srv.Close()

	client := &github.HTTPClient{
		Token:      "token",
		HTTPClient: srv.Client(),
		BaseURL:    srv.URL,
	}
	result, err := client.MergePullRequest(context.Background(), github.MergePullRequestRequest{
		Repository:  github.Repository{Owner: "acme", Name: "mod"},
		Number:      9,
		CommitTitle: "chore(repave): upgrade",
	})
	if err != nil {
		t.Fatalf("MergePullRequest: %v", err)
	}
	if method != http.MethodPut {
		t.Fatalf("method = %q, want PUT", method)
	}
	if !result.Merged || result.SHA != "abc123" {
		t.Fatalf("result = %+v", result)
	}
}
