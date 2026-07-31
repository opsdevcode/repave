package inventory

import (
	"context"
	"os"
	"path/filepath"
)

// StaticRepoFetcher materializes dir with Content for in-package tests.
type StaticRepoFetcher struct {
	Content []byte
	Err     error
	Calls   int
}

// Fetch writes Content to dir/repave.yaml or returns Err.
func (f *StaticRepoFetcher) Fetch(_ context.Context, _ string, dir string) error {
	f.Calls++
	if f.Err != nil {
		return f.Err
	}
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return err
	}
	if len(f.Content) == 0 {
		return nil
	}
	return os.WriteFile(filepath.Join(dir, "repave.yaml"), f.Content, 0o600)
}
