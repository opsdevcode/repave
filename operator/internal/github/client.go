package github

import (
	"context"
	"fmt"
)

// CreatePullRequestRequest is the input for opening a remediation PR.
type CreatePullRequestRequest struct {
	Repository Repository
	Title        string
	Body         string
	HeadBranch   string
	BaseBranch   string
}

// PullRequest is a minimal view of a created GitHub pull request.
type PullRequest struct {
	Number  int
	HTMLURL string
	Title   string
	State   string
}

// Client opens pull requests on GitHub.
type Client interface {
	CreatePullRequest(ctx context.Context, req CreatePullRequestRequest) (PullRequest, error)
}

// RecordingClient stores the last request for tests.
type RecordingClient struct {
	LastRequest CreatePullRequestRequest
	Response    PullRequest
	Err         error
	Calls       int
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
