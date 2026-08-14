package github

import (
	"context"
	"fmt"
)

// CreatePullRequestRequest is the input for opening a remediation PR.
type CreatePullRequestRequest struct {
	Repository Repository
	Title      string
	Body       string
	HeadBranch string
	BaseBranch string
	Labels     []string
}

// PullRequest is a minimal view of a created GitHub pull request.
type PullRequest struct {
	Number  int
	HTMLURL string
	Title   string
	State   string
}

// MergePullRequestRequest is the input for squash-merging a remediation PR.
type MergePullRequestRequest struct {
	Repository  Repository
	Number      int
	CommitTitle string
}

// MergeResult is the GitHub merge API outcome.
type MergeResult struct {
	Merged bool
	SHA    string
}

// Client opens and optionally merges pull requests on GitHub.
type Client interface {
	CreatePullRequest(ctx context.Context, req CreatePullRequestRequest) (PullRequest, error)
	MergePullRequest(ctx context.Context, req MergePullRequestRequest) (MergeResult, error)
}

// RecordingClient stores the last request for tests.
type RecordingClient struct {
	LastRequest CreatePullRequestRequest
	LastMerge   MergePullRequestRequest
	Response    PullRequest
	MergeResult MergeResult
	Err         error
	MergeErr    error
	Calls       int
	MergeCalls  int
}

func (r *RecordingClient) CreatePullRequest(
	_ context.Context,
	req CreatePullRequestRequest,
) (PullRequest, error) {
	r.Calls++
	r.LastRequest = req
	if r.Err != nil {
		return PullRequest{}, r.Err
	}
	if r.Response.HTMLURL == "" {
		return PullRequest{
			Number:  1,
			HTMLURL: fmt.Sprintf("%s/pull/1", req.Repository.WebURL()),
			Title:   req.Title,
			State:   "open",
		}, nil
	}
	return r.Response, nil
}

func (r *RecordingClient) MergePullRequest(
	_ context.Context,
	req MergePullRequestRequest,
) (MergeResult, error) {
	r.MergeCalls++
	r.LastMerge = req
	if r.MergeErr != nil {
		return MergeResult{}, r.MergeErr
	}
	if r.MergeResult.SHA == "" && !r.MergeResult.Merged {
		return MergeResult{Merged: true, SHA: "merge-sha"}, nil
	}
	return r.MergeResult, nil
}
