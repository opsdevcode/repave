package provenance_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/provenance"
)

func TestReadPinsFromRepoRoot(t *testing.T) {
	root := filepath.Join("..", "..", "testdata", "modules", "terraform-minimal")
	abs, err := filepath.Abs(root)
	if err != nil {
		t.Fatal(err)
	}

	pins, err := provenance.ReadPinsFromRepoRoot(abs)
	if err != nil {
		t.Fatalf("ReadPinsFromRepoRoot: %v", err)
	}
	want := drift.PinSet{
		BlueprintName:    "terraform-module-generic",
		BlueprintVersion: "0.1.0",
		StandardSource:   "examples/standards",
		StandardVersion:  "0.4.0",
	}
	if pins != want {
		t.Fatalf("got %+v want %+v", pins, want)
	}
}

func TestReadPinsFromRepoRoot_missingFile(t *testing.T) {
	dir := t.TempDir()
	_, err := provenance.ReadPinsFromRepoRoot(dir)
	if err == nil {
		t.Fatal("expected error for missing repave.yaml")
	}
}

func TestParsePins_rejectsWrongKind(t *testing.T) {
	_, err := provenance.ParsePins([]byte("apiVersion: repave.dev/v1beta1\nkind: Wrong\nspec: {}\n"))
	if err == nil {
		t.Fatal("expected kind validation error")
	}
}

func TestParsePins_fromFileRoundTrip(t *testing.T) {
	path := filepath.Join("..", "..", "testdata", "modules", "terraform-minimal", "repave.yaml")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := provenance.ParsePins(data); err != nil {
		t.Fatalf("ParsePins: %v", err)
	}
}
