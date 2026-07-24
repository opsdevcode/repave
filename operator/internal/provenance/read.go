package provenance

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"

	"github.com/opsdevcode/repave/operator/internal/drift"
)

const (
	// DefaultFilename is the provenance file written by the repave engine.
	DefaultFilename = "repave.yaml"
	expectedAPIVersion = "repave.dev/v1beta1"
	expectedKind       = "GoldenPathArtifact"
)

type document struct {
	APIVersion string `yaml:"apiVersion"`
	Kind       string `yaml:"kind"`
	Spec       struct {
		Blueprint struct {
			Name    string `yaml:"name"`
			Version string `yaml:"version"`
		} `yaml:"blueprint"`
		Standard struct {
			Source  string `yaml:"source"`
			Version string `yaml:"version"`
		} `yaml:"standard"`
	} `yaml:"spec"`
}

// ReadPinsFromRepoRoot loads repave.yaml under repoRoot and returns blueprint/standard pins.
func ReadPinsFromRepoRoot(repoRoot string) (drift.PinSet, error) {
	path := filepath.Join(repoRoot, DefaultFilename)
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return drift.PinSet{}, fmt.Errorf("%s: %w", path, err)
		}
		return drift.PinSet{}, fmt.Errorf("read provenance: %w", err)
	}
	return ParsePins(data)
}

// ParsePins extracts pins from GoldenPathArtifact YAML bytes.
func ParsePins(data []byte) (drift.PinSet, error) {
	var doc document
	if err := yaml.Unmarshal(data, &doc); err != nil {
		return drift.PinSet{}, fmt.Errorf("parse provenance yaml: %w", err)
	}
	if doc.APIVersion != expectedAPIVersion {
		return drift.PinSet{}, fmt.Errorf("unsupported apiVersion %q (want %s)", doc.APIVersion, expectedAPIVersion)
	}
	if doc.Kind != expectedKind {
		return drift.PinSet{}, fmt.Errorf("unsupported kind %q (want %s)", doc.Kind, expectedKind)
	}

	pins := drift.PinSet{
		BlueprintName:    strings.TrimSpace(doc.Spec.Blueprint.Name),
		BlueprintVersion: strings.TrimSpace(doc.Spec.Blueprint.Version),
		StandardSource:   strings.TrimSpace(doc.Spec.Standard.Source),
		StandardVersion:  strings.TrimSpace(doc.Spec.Standard.Version),
	}
	if err := pins.Validate(); err != nil {
		return drift.PinSet{}, err
	}
	return pins, nil
}
