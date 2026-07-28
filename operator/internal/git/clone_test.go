package git

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// newFixtureRemote creates a real local git repository containing repave.yaml and returns
// a file:// URL, so clone behavior is exercised without network access.
func newFixtureRemote(t *testing.T) string {
	t.Helper()

	if _, err := exec.LookPath("git"); err != nil {
		t.Skip("git not installed")
	}

	dir := t.TempDir()
	source := filepath.Join(dir, "source")
	if err := os.MkdirAll(source, 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(source, "repave.yaml"), []byte("apiVersion: repave.dev/v1beta1\n"), 0o600); err != nil {
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
		if out, err := cmd.CombinedOutput(); err != nil {
			t.Fatalf("git %s: %v: %s", strings.Join(args, " "), err, out)
		}
	}
	return "file://" + source
}

func TestClone_shallowCopiesWorkingTree(t *testing.T) {
	remote := newFixtureRemote(t)
	target := filepath.Join(t.TempDir(), "clone")

	if err := Clone(context.Background(), CloneOptions{RepoURL: remote, Dir: target}); err != nil {
		t.Fatalf("Clone: %v", err)
	}

	if _, err := os.Stat(filepath.Join(target, "repave.yaml")); err != nil {
		t.Fatalf("expected repave.yaml in clone: %v", err)
	}
}

func TestClone_requiresURLAndDir(t *testing.T) {
	if err := Clone(context.Background(), CloneOptions{Dir: t.TempDir()}); err == nil {
		t.Fatal("expected error for missing repository URL")
	}
	if err := Clone(context.Background(), CloneOptions{RepoURL: "https://example.com/x.git"}); err == nil {
		t.Fatal("expected error for missing target directory")
	}
}

func TestClone_redactsTokenFromError(t *testing.T) {
	const token = "ghp_supersecrettoken"
	target := filepath.Join(t.TempDir(), "clone")

	err := Clone(context.Background(), CloneOptions{
		RepoURL: "https://example.invalid/opsdevcode/missing.git",
		Dir:     target,
		Token:   token,
	})
	if err == nil {
		t.Fatal("expected clone of unreachable host to fail")
	}
	if strings.Contains(err.Error(), token) {
		t.Fatalf("token leaked in error: %v", err)
	}
	if !strings.Contains(err.Error(), "***") {
		t.Fatalf("expected redaction marker in error: %v", err)
	}
}

func TestCredentialRemote_preservesHost(t *testing.T) {
	remote, err := credentialRemote("https://github.example.com/acme/module.git", "tok")
	if err != nil {
		t.Fatalf("credentialRemote: %v", err)
	}
	if !strings.HasPrefix(remote, "https://x-access-token:tok@github.example.com/") {
		t.Fatalf("unexpected remote %q", remote)
	}
}
