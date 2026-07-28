package inventory_test

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// newLocalGitRemote builds a real git repository from the terraform-minimal fixture and
// returns a file:// URL so GitFetcher is exercised without network access.
func newLocalGitRemote(t *testing.T) string {
	t.Helper()

	if _, err := exec.LookPath("git"); err != nil {
		t.Skip("git not installed")
	}

	source := filepath.Join(t.TempDir(), "source")
	if err := os.MkdirAll(source, 0o750); err != nil {
		t.Fatal(err)
	}
	provenance, err := os.ReadFile(filepath.Join(fixtureRoot(t), "repave.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(source, "repave.yaml"), provenance, 0o600); err != nil {
		t.Fatal(err)
	}

	for _, args := range [][]string{
		{"init", "--initial-branch", "main"},
		{"config", "user.email", "test@example.com"},
		{"config", "user.name", "repave test"},
		{"add", "."},
		{"commit", "-m", "fixture"},
	} {
		cmd := exec.Command("git", args...)
		cmd.Dir = source
		if out, cmdErr := cmd.CombinedOutput(); cmdErr != nil {
			t.Fatalf("git %s: %v: %s", strings.Join(args, " "), cmdErr, out)
		}
	}
	return "file://" + source
}
