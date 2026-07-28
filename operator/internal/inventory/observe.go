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

// Workspace is a filesystem view of a registered repository. Remote repos are cloned into
// a temporary directory; local repos point at the working tree in place.
type Workspace struct {
	// Path is the repository root to read provenance from and re-render against.
	Path string

	// Remote is true when Path is a clone rather than the user's working tree.
	Remote bool

	tempDir string
}

// Close removes a cloned workspace. Local working trees are left untouched.
func (w *Workspace) Close() {
	if w == nil || w.tempDir == "" {
		return
	}
	_ = os.RemoveAll(w.tempDir)
	w.tempDir = ""
}

// Materialize resolves a spec to a Workspace. Callers must Close the result.
func Materialize(
	ctx context.Context,
	spec repavev1alpha1.GoldenPathRepoSpec,
	fetcher RepoFetcher,
) (*Workspace, error) {
	switch {
	case spec.LocalPath != "":
		return &Workspace{Path: spec.LocalPath}, nil
	case spec.RepoURL != "":
		if fetcher == nil {
			return nil, ErrRemoteRepoNotSupported
		}
		return cloneWorkspace(ctx, spec.RepoURL, fetcher)
	default:
		return nil, fmt.Errorf("spec.repoURL or spec.localPath is required")
	}
}

func cloneWorkspace(ctx context.Context, repoURL string, fetcher RepoFetcher) (*Workspace, error) {
	tempDir, err := os.MkdirTemp("", "repave-inventory-")
	if err != nil {
		return nil, fmt.Errorf("create inventory workspace: %w", err)
	}

	repoDir := filepath.Join(tempDir, "repo")
	if err := fetcher.Fetch(ctx, repoURL, repoDir); err != nil {
		_ = os.RemoveAll(tempDir)
		return nil, fmt.Errorf("%w: %s", ErrRemoteFetchFailed, err)
	}
	return &Workspace{Path: repoDir, Remote: true, tempDir: tempDir}, nil
}

// PinsFromWorkspace reads observed blueprint/standard pins from a materialized repo.
func PinsFromWorkspace(workspace *Workspace) (drift.PinSet, error) {
	if workspace == nil || workspace.Path == "" {
		return drift.PinSet{}, fmt.Errorf("workspace is not materialized")
	}
	return provenance.ReadPinsFromRepoRoot(workspace.Path)
}

// ObservePins materializes the repo, reads its pins, and releases any clone.
func ObservePins(
	ctx context.Context,
	spec repavev1alpha1.GoldenPathRepoSpec,
	fetcher RepoFetcher,
) (drift.PinSet, error) {
	workspace, err := Materialize(ctx, spec, fetcher)
	if err != nil {
		return drift.PinSet{}, err
	}
	defer workspace.Close()
	return PinsFromWorkspace(workspace)
}

// EvaluateDesiredObserved compares desired spec pins to observed repo pins.
func EvaluateDesiredObserved(desired, observed drift.PinSet) (outOfDate bool) {
	return drift.PinsDiffer(desired, observed)
}
