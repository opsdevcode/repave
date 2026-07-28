package inventory_test

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"testing"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/inventory"
)

func fixtureRoot(t *testing.T) string {
	t.Helper()
	root, err := filepath.Abs(filepath.Join("..", "..", "testdata", "modules", "terraform-minimal"))
	if err != nil {
		t.Fatal(err)
	}
	return root
}

// copyFetcher stands in for a git clone by copying the local fixture into dir.
type copyFetcher struct {
	source string
	calls  int
}

func (f *copyFetcher) Fetch(_ context.Context, _ string, dir string) error {
	f.calls++
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return err
	}
	data, err := os.ReadFile(filepath.Join(f.source, "repave.yaml"))
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(dir, "repave.yaml"), data, 0o600)
}

type failingFetcher struct{}

func (failingFetcher) Fetch(_ context.Context, _ string, _ string) error {
	return fmt.Errorf("dial tcp: connection refused")
}

func TestObservePins_localFixture(t *testing.T) {
	spec := repavev1alpha1.GoldenPathRepoSpec{LocalPath: fixtureRoot(t)}
	pins, err := inventory.ObservePins(context.Background(), spec, nil)
	if err != nil {
		t.Fatalf("ObservePins: %v", err)
	}
	if pins.BlueprintName != "terraform-module-generic" {
		t.Fatalf("unexpected blueprint %q", pins.BlueprintName)
	}
}

func TestObservePins_remoteReadsClonedProvenance(t *testing.T) {
	fetcher := &copyFetcher{source: fixtureRoot(t)}
	spec := repavev1alpha1.GoldenPathRepoSpec{RepoURL: "https://github.com/example/module.git"}

	pins, err := inventory.ObservePins(context.Background(), spec, fetcher)
	if err != nil {
		t.Fatalf("ObservePins: %v", err)
	}
	if pins.BlueprintName != "terraform-module-generic" {
		t.Fatalf("unexpected blueprint %q", pins.BlueprintName)
	}
	if fetcher.calls != 1 {
		t.Fatalf("expected one fetch, got %d", fetcher.calls)
	}
}

func TestObservePins_remoteFetchFailureIsTransient(t *testing.T) {
	spec := repavev1alpha1.GoldenPathRepoSpec{RepoURL: "https://github.com/example/module.git"}

	_, err := inventory.ObservePins(context.Background(), spec, failingFetcher{})
	if !errors.Is(err, inventory.ErrRemoteFetchFailed) {
		t.Fatalf("expected ErrRemoteFetchFailed, got %v", err)
	}
}

func TestObservePins_remoteWithoutFetcherUnsupported(t *testing.T) {
	spec := repavev1alpha1.GoldenPathRepoSpec{RepoURL: "https://github.com/example/module.git"}

	_, err := inventory.ObservePins(context.Background(), spec, nil)
	if !errors.Is(err, inventory.ErrRemoteRepoNotSupported) {
		t.Fatalf("expected ErrRemoteRepoNotSupported, got %v", err)
	}
}

func TestObservePins_requiresLocation(t *testing.T) {
	_, err := inventory.ObservePins(context.Background(), repavev1alpha1.GoldenPathRepoSpec{}, nil)
	if err == nil {
		t.Fatal("expected error when neither localPath nor repoURL is set")
	}
}

func TestGitFetcher_clonesLocalRemote(t *testing.T) {
	remote := newLocalGitRemote(t)
	dir := filepath.Join(t.TempDir(), "repo")

	if err := (inventory.GitFetcher{}).Fetch(context.Background(), remote, dir); err != nil {
		t.Fatalf("Fetch: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dir, "repave.yaml")); err != nil {
		t.Fatalf("expected repave.yaml in clone: %v", err)
	}
}
