package inventory_test

import (
	"errors"
	"path/filepath"
	"testing"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/inventory"
)

func TestObservePins_localFixture(t *testing.T) {
	root, err := filepath.Abs(filepath.Join("..", "..", "testdata", "modules", "terraform-minimal"))
	if err != nil {
		t.Fatal(err)
	}
	spec := repavev1alpha1.GoldenPathRepoSpec{LocalPath: root}
	pins, err := inventory.ObservePins(spec)
	if err != nil {
		t.Fatalf("ObservePins: %v", err)
	}
	if pins.BlueprintName != "terraform-module-generic" {
		t.Fatalf("unexpected blueprint %q", pins.BlueprintName)
	}
}

func TestObservePins_remoteUnsupported(t *testing.T) {
	spec := repavev1alpha1.GoldenPathRepoSpec{RepoURL: "https://github.com/example/module.git"}
	_, err := inventory.ObservePins(spec)
	if !errors.Is(err, inventory.ErrRemoteRepoNotSupported) {
		t.Fatalf("expected ErrRemoteRepoNotSupported, got %v", err)
	}
}
