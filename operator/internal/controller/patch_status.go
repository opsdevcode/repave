package controller

import (
	"context"

	"sigs.k8s.io/controller-runtime/pkg/client"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
)

// patchGoldenPathRepoStatus updates status using a merge patch to reduce conflict.
func patchGoldenPathRepoStatus(
	ctx context.Context,
	c client.Client,
	repo *repavev1alpha1.GoldenPathRepo,
	mutate func(*repavev1alpha1.GoldenPathRepo),
) error {
	base := client.MergeFrom(repo.DeepCopy())
	mutate(repo)
	repo.Status.ObservedGeneration = repo.Generation
	return c.Status().Patch(ctx, repo, base)
}
