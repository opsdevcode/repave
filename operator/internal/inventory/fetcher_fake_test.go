package inventory_test

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/inventory"
)

func TestStaticRepoFetcher_writesProvenance(t *testing.T) {
	content, err := os.ReadFile(filepath.Join(fixtureRoot(t), "repave.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	fetcher := &inventory.StaticRepoFetcher{Content: content}
	dir := t.TempDir()

	if err := fetcher.Fetch(context.Background(), "https://example.com/repo.git", dir); err != nil {
		t.Fatalf("Fetch: %v", err)
	}
	if fetcher.Calls != 1 {
		t.Fatalf("Calls = %d, want 1", fetcher.Calls)
	}

	pins, err := inventory.ObservePins(
		context.Background(),
		repavev1beta1.GoldenPathRepoSpec{RepoURL: "https://example.com/repo.git"},
		fetcher,
	)
	if err != nil {
		t.Fatalf("ObservePins: %v", err)
	}
	if pins.BlueprintName != "terraform-module-generic" {
		t.Fatalf("BlueprintName = %q", pins.BlueprintName)
	}
}
