package fleetsync

import (
	"context"
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
)

// SyncGoldenPathRepos creates, updates, and prunes fleet-managed GoldenPathRepos.
func SyncGoldenPathRepos(
	ctx context.Context,
	c client.Client,
	cfg Config,
	entries []Entry,
) (created int, updated int, pruned int, err error) {
	logger := log.FromContext(ctx)
	desired := map[string]Entry{}
	for _, entry := range entries {
		name := ResourceName(entry.RepoURL)
		desired[name] = entry
	}

	var existing repavev1beta1.GoldenPathRepoList
	if err := c.List(ctx, &existing, client.InNamespace(cfg.Namespace)); err != nil {
		return 0, 0, 0, err
	}

	managed := map[string]repavev1beta1.GoldenPathRepo{}
	for i := range existing.Items {
		gpr := existing.Items[i]
		if gpr.Labels[managedByLabel] != managedByValue {
			continue
		}
		managed[gpr.Name] = gpr
	}

	for name, entry := range desired {
		current, ok := managed[name]
		desiredGPR := buildGoldenPathRepo(cfg, name, entry)
		if !ok {
			if err := c.Create(ctx, desiredGPR); err != nil {
				return created, updated, pruned, fmt.Errorf("create GoldenPathRepo %s: %w", name, err)
			}
			created++
			continue
		}
		if goldenPathRepoSpecChanged(&current, desiredGPR) {
			patch := current.DeepCopy()
			patch.Spec = desiredGPR.Spec
			patch.Labels = desiredGPR.Labels
			patch.Annotations = desiredGPR.Annotations
			if err := c.Patch(ctx, patch, client.MergeFrom(current.DeepCopy())); err != nil {
				return created, updated, pruned, fmt.Errorf("patch GoldenPathRepo %s: %w", name, err)
			}
			updated++
		}
		delete(managed, name)
	}

	for name, orphan := range managed {
		if err := c.Delete(ctx, &orphan); err != nil {
			return created, updated, pruned, fmt.Errorf("delete GoldenPathRepo %s: %w", name, err)
		}
		pruned++
		logger.Info("pruned fleet-managed GoldenPathRepo", "name", name, "namespace", cfg.Namespace)
	}

	return created, updated, pruned, nil
}

func buildGoldenPathRepo(cfg Config, name string, entry Entry) *repavev1beta1.GoldenPathRepo {
	labels := map[string]string{
		managedByLabel: managedByValue,
	}
	annotations := map[string]string{}
	if entry.Owner != "" {
		annotations["repave.dev/owner"] = entry.Owner
	}
	spec := repavev1beta1.GoldenPathRepoSpec{
		RepoURL: entry.RepoURL,
		DesiredPins: repavev1beta1.DesiredPins{
			BlueprintName:    entry.BlueprintName,
			BlueprintVersion: entry.BlueprintVersion,
			StandardSource:   entry.StandardSource,
			StandardVersion:  entry.StandardVersion,
		},
	}
	if cfg.EnableRemediation {
		spec.Remediation = repavev1beta1.RemediationSpec{Enabled: true}
	}
	return &repavev1beta1.GoldenPathRepo{
		ObjectMeta: metav1.ObjectMeta{
			Name:        name,
			Namespace:   cfg.Namespace,
			Labels:      labels,
			Annotations: annotations,
		},
		Spec: spec,
	}
}

func goldenPathRepoSpecChanged(current, desired *repavev1beta1.GoldenPathRepo) bool {
	if current.Spec.RepoURL != desired.Spec.RepoURL {
		return true
	}
	if current.Spec.DesiredPins != desired.Spec.DesiredPins {
		return true
	}
	if current.Spec.Remediation.Enabled != desired.Spec.Remediation.Enabled {
		return true
	}
	if current.Labels[managedByLabel] != managedByValue {
		return true
	}
	desiredOwner := desired.Annotations["repave.dev/owner"]
	currentOwner := current.Annotations["repave.dev/owner"]
	return desiredOwner != currentOwner
}
