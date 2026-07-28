package inventory

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/git"
	"github.com/opsdevcode/repave/operator/internal/provenance"
)

// ErrRemoteRepoNotSupported is returned when a repoURL spec is observed without a fetcher.
var ErrRemoteRepoNotSupported = errors.New("repoURL inventory requires a repo fetcher")

// ErrRemoteFetchFailed marks a transient remote failure (network, auth, missing ref) so
// callers can requeue with backoff instead of treating it as user misconfiguration.
var ErrRemoteFetchFailed = errors.New("remote repository fetch failed")

// RepoFetcher materializes a remote repository into dir for read-only inventory.
type RepoFetcher interface {
	Fetch(ctx context.Context, repoURL, dir string) error
}

// GitFetcher shallow-clones remotes. Token is optional and only used for HTTPS.
type GitFetcher struct {
	Token string
}

// Fetch clones repoURL into dir.
func (f GitFetcher) Fetch(ctx context.Context, repoURL, dir string) error {
	return git.Clone(ctx, git.CloneOptions{RepoURL: repoURL, Dir: dir, Token: f.Token})
}

// ObservePins reads observed blueprint/standard pins from the registered repository.
// localPath reads the working tree in place; repoURL is cloned into a temporary
// workspace that is removed before returning.
func ObservePins(
	ctx context.Context,
	spec repavev1alpha1.GoldenPathRepoSpec,
	fetcher RepoFetcher,
) (drift.PinSet, error) {
	switch {
	case spec.LocalPath != "":
		return provenance.ReadPinsFromRepoRoot(spec.LocalPath)
	case spec.RepoURL != "":
		if fetcher == nil {
			return drift.PinSet{}, ErrRemoteRepoNotSupported
		}
		return observeRemote(ctx, spec.RepoURL, fetcher)
	default:
		return drift.PinSet{}, fmt.Errorf("spec.repoURL or spec.localPath is required")
	}
}

func observeRemote(ctx context.Context, repoURL string, fetcher RepoFetcher) (drift.PinSet, error) {
	workspace, err := os.MkdirTemp("", "repave-inventory-")
	if err != nil {
		return drift.PinSet{}, fmt.Errorf("create inventory workspace: %w", err)
	}
	defer func() {
		_ = os.RemoveAll(workspace)
	}()

	repoDir := filepath.Join(workspace, "repo")
	if err := fetcher.Fetch(ctx, repoURL, repoDir); err != nil {
		return drift.PinSet{}, fmt.Errorf("%w: %s", ErrRemoteFetchFailed, err)
	}
	return provenance.ReadPinsFromRepoRoot(repoDir)
}

// EvaluateDesiredObserved compares desired spec pins to observed repo pins.
func EvaluateDesiredObserved(desired, observed drift.PinSet) (outOfDate bool) {
	return drift.PinsDiffer(desired, observed)
}
