package fleetsync

import (
	"context"
	"time"

	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"
)

// Runnable periodically syncs GoldenPathRepo objects from the fleet registry file.
type Runnable struct {
	Client client.Client
	Config Config
}

// Start implements manager.Runnable.
func (r *Runnable) Start(ctx context.Context) error {
	logger := log.FromContext(ctx)
	logger.Info(
		"fleet registry sync enabled",
		"path", r.Config.RegistryPath,
		"namespace", r.Config.Namespace,
		"interval", r.Config.Interval.String(),
	)
	if err := r.syncOnce(ctx); err != nil {
		logger.Error(err, "initial fleet registry sync failed")
	}
	ticker := time.NewTicker(r.Config.Interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			if err := r.syncOnce(ctx); err != nil {
				logger.Error(err, "fleet registry sync failed")
			}
		}
	}
}

func (r *Runnable) syncOnce(ctx context.Context) error {
	logger := log.FromContext(ctx)
	entries, err := ReadRegistry(r.Config.RegistryPath)
	if err != nil {
		return err
	}
	created, updated, pruned, err := SyncGoldenPathRepos(ctx, r.Client, r.Config, entries)
	if err != nil {
		return err
	}
	if created > 0 || updated > 0 || pruned > 0 {
		logger.Info(
			"fleet registry sync complete",
			"entries", len(entries),
			"created", created,
			"updated", updated,
			"pruned", pruned,
		)
	}
	return nil
}

// NeedLeaderElection returns true so only one operator pod syncs the fleet.
func (r *Runnable) NeedLeaderElection() bool {
	return true
}
