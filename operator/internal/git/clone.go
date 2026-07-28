package git

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
)

// DefaultCloneDepth keeps inventory clones shallow; only repave.yaml at HEAD is read.
const DefaultCloneDepth = 1

// CloneOptions configures a read-only clone for remote inventory.
type CloneOptions struct {
	// RepoURL is the git remote (https or ssh).
	RepoURL string

	// Dir is the target directory; parents are created when missing.
	Dir string

	// Token authenticates HTTPS remotes. Empty means public repo or SSH credentials.
	Token string

	// Depth overrides DefaultCloneDepth.
	Depth int
}

// Clone shallow-clones RepoURL into Dir. Read-only: no remote is left configured with
// credentials beyond the clone URL, and token material is redacted from errors.
func Clone(ctx context.Context, opts CloneOptions) error {
	repoURL := strings.TrimSpace(opts.RepoURL)
	dir := strings.TrimSpace(opts.Dir)
	if repoURL == "" || dir == "" {
		return fmt.Errorf("repository URL and target directory are required")
	}
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return fmt.Errorf("create clone directory: %w", err)
	}

	depth := opts.Depth
	if depth <= 0 {
		depth = DefaultCloneDepth
	}

	remote := repoURL
	token := strings.TrimSpace(opts.Token)
	if token != "" && isHTTPRemote(repoURL) {
		authenticated, err := credentialRemote(repoURL, token)
		if err != nil {
			return err
		}
		remote = authenticated
	}

	return runGitSecret(ctx, "", token,
		"clone", "--depth", strconv.Itoa(depth), "--single-branch", "--no-tags", remote, dir)
}

func isHTTPRemote(repoURL string) bool {
	return strings.HasPrefix(repoURL, "https://") || strings.HasPrefix(repoURL, "http://")
}

// credentialRemote injects a token into an HTTPS remote while preserving the host, so
// self-hosted GitHub Enterprise and other forges keep working.
func credentialRemote(repoURL, token string) (string, error) {
	parsed, err := url.Parse(repoURL)
	if err != nil {
		return "", fmt.Errorf("parse repository URL: %w", err)
	}
	if parsed.Host == "" {
		return "", fmt.Errorf("repository URL %q has no host", repoURL)
	}
	parsed.User = url.UserPassword("x-access-token", token)
	return parsed.String(), nil
}
