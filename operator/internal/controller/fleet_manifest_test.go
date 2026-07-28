package controller

import (
	"os"
	"path/filepath"
	"testing"

	"sigs.k8s.io/yaml"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
)

// The engine renders these fixtures with `repave fleet-manifests`; they are checked in so a
// field rename on either side fails here rather than at apply time in a user's cluster.
// Regenerate with: cd engine && uv run python -m pytest tests/test_fleet_manifests.py
const fleetFixtureDir = "../../testdata/fleet"

func TestFleetManifestsDecodeStrictly(t *testing.T) {
	entries, err := os.ReadDir(fleetFixtureDir)
	if err != nil {
		t.Fatalf("read fixture dir: %v", err)
	}
	if len(entries) == 0 {
		t.Fatal("expected rendered GoldenPathRepo fixtures")
	}

	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".yaml" {
			continue
		}
		t.Run(entry.Name(), func(t *testing.T) {
			data, err := os.ReadFile(filepath.Join(fleetFixtureDir, entry.Name()))
			if err != nil {
				t.Fatalf("read fixture: %v", err)
			}

			var repo repavev1alpha1.GoldenPathRepo
			// Strict decoding rejects unknown or misspelled fields, which is the point:
			// the engine must emit exactly the CRD's field names.
			if err := yaml.UnmarshalStrict(data, &repo); err != nil {
				t.Fatalf("manifest does not match the GoldenPathRepo API: %v", err)
			}

			if repo.APIVersion != "repave.dev/v1alpha1" {
				t.Errorf("apiVersion = %q, want repave.dev/v1alpha1", repo.APIVersion)
			}
			if repo.Kind != "GoldenPathRepo" {
				t.Errorf("kind = %q, want GoldenPathRepo", repo.Kind)
			}
			if repo.Name == "" {
				t.Error("metadata.name is empty")
			}
			if repo.Spec.RepoURL == "" {
				t.Error("spec.repoURL is empty; the operator would have nothing to clone")
			}
			if repo.Spec.LocalPath != "" {
				t.Errorf("spec.localPath = %q, want empty for registry-sourced repos", repo.Spec.LocalPath)
			}

			pins := repo.Spec.DesiredPins
			for field, value := range map[string]string{
				"blueprintName":    pins.BlueprintName,
				"blueprintVersion": pins.BlueprintVersion,
				"standardSource":   pins.StandardSource,
				"standardVersion":  pins.StandardVersion,
			} {
				if value == "" {
					t.Errorf("desiredPins.%s is empty, but the CRD requires MinLength=1", field)
				}
			}
		})
	}
}

func TestFleetManifestVersionsSurviveAsStrings(t *testing.T) {
	// A two-component version such as "1.0" is a YAML float unless quoted; if the engine
	// emitted it bare, strict decoding into a string field would fail.
	data, err := os.ReadFile(filepath.Join(fleetFixtureDir, "acme-opa-guardrails.yaml"))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}

	var repo repavev1alpha1.GoldenPathRepo
	if err := yaml.UnmarshalStrict(data, &repo); err != nil {
		t.Fatalf("decode: %v", err)
	}

	if repo.Spec.DesiredPins.BlueprintVersion != "1.0" {
		t.Errorf("blueprintVersion = %q, want \"1.0\"", repo.Spec.DesiredPins.BlueprintVersion)
	}
}
