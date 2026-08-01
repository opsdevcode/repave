package fleetsync

import (
	"os"
	"path/filepath"
	"testing"
)

func TestReadRegistryFoldsEvents(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "registry.jsonl")
	content := "" +
		`{"event":"register","repo_url":"https://github.com/acme/one","blueprint_name":"bp","blueprint_version":"1.0.0","standard_source":"s","standard_version":"1.0"}` + "\n" +
		`{"event":"register","repo_url":"https://github.com/acme/two","blueprint_name":"bp","blueprint_version":"2.0.0","standard_source":"s","standard_version":"2.0"}` + "\n" +
		`{"event":"unregister","repo_url":"https://github.com/acme/one"}` + "\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	entries, err := ReadRegistry(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 entry, got %d", len(entries))
	}
	if entries[0].RepoURL != "https://github.com/acme/two" {
		t.Fatalf("unexpected repo: %s", entries[0].RepoURL)
	}
	if entries[0].BlueprintVersion != "2.0.0" {
		t.Fatalf("unexpected blueprint version: %s", entries[0].BlueprintVersion)
	}
}

func TestReadRegistryMissingFile(t *testing.T) {
	entries, err := ReadRegistry(filepath.Join(t.TempDir(), "missing.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	if entries != nil {
		t.Fatalf("expected nil slice, got %#v", entries)
	}
}
