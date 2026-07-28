package git

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// PushBranch pushes a local branch to origin using a token-authenticated HTTPS remote.
func PushBranch(ctx context.Context, repoDir, repoURL, branch, token string) error {
	repoDir = strings.TrimSpace(repoDir)
	branch = strings.TrimSpace(branch)
	token = strings.TrimSpace(token)
	if repoDir == "" || branch == "" {
		return fmt.Errorf("repo directory and branch are required")
	}
	if token == "" {
		return fmt.Errorf("git push requires a GitHub token")
	}

	ownerRepo, err := authenticatedRemote(repoURL, token)
	if err != nil {
		return err
	}

	if err := runGit(ctx, repoDir, "remote", "get-url", "origin"); err != nil {
		if err := runGit(ctx, repoDir, "remote", "add", "origin", ownerRepo); err != nil {
			return err
		}
	} else if err := runGit(ctx, repoDir, "remote", "set-url", "origin", ownerRepo); err != nil {
		return err
	}

	return runGitSecret(ctx, repoDir, token, "push", "-u", "origin", branch)
}

func authenticatedRemote(repoURL, token string) (string, error) {
	trimmed := strings.TrimSpace(repoURL)
	if trimmed == "" {
		return "", fmt.Errorf("repository URL is required for git push")
	}
	trimmed = strings.TrimPrefix(trimmed, "https://")
	trimmed = strings.TrimPrefix(trimmed, "http://")
	trimmed = strings.TrimPrefix(trimmed, "git@github.com:")
	trimmed = strings.TrimSuffix(trimmed, ".git")
	parts := strings.Split(strings.Trim(trimmed, "/"), "/")
	if len(parts) < 2 {
		return "", fmt.Errorf("unable to parse owner/name from %q", repoURL)
	}
	owner := parts[len(parts)-2]
	name := parts[len(parts)-1]
	return fmt.Sprintf("https://x-access-token:%s@github.com/%s/%s.git", token, owner, name), nil
}

func runGit(ctx context.Context, dir string, args ...string) error {
	return runGitSecret(ctx, dir, "", args...)
}

// runGitSecret runs git non-interactively and strips secret from the command line and
// output before it can reach controller logs or CR status.
func runGitSecret(ctx context.Context, dir, secret string, args ...string) error {
	cmd := exec.CommandContext(ctx, "git", args...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(),
		"GIT_TERMINAL_PROMPT=0",
		"GIT_ASKPASS=",
		"GIT_SSH_COMMAND=ssh -o BatchMode=yes",
	)
	out, err := cmd.CombinedOutput()
	if err != nil {
		msg := strings.TrimSpace(string(out))
		if msg == "" {
			msg = err.Error()
		}
		return fmt.Errorf("git %s: %s", redactSecret(strings.Join(args, " "), secret), redactSecret(msg, secret))
	}
	return nil
}

func redactSecret(text, secret string) string {
	if secret == "" {
		return text
	}
	return strings.ReplaceAll(text, secret, "***")
}
