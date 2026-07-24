package controller

import (
	"context"

	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/handler"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
)

func (r *GoldenPathRepoReconciler) enqueueGoldenPathReposForBlueprint(
	ctx context.Context,
	obj client.Object,
) []reconcile.Request {
	bp, ok := obj.(*repavev1alpha1.Blueprint)
	if !ok {
		return nil
	}

	var list repavev1alpha1.GoldenPathRepoList
	if err := r.List(ctx, &list, client.InNamespace(bp.Namespace)); err != nil {
		return nil
	}

	requests := make([]reconcile.Request, 0, len(list.Items))
	for i := range list.Items {
		gpr := &list.Items[i]
		if !goldenPathRepoWatchesBlueprint(gpr, bp.Name) {
			continue
		}
		requests = append(requests, reconcile.Request{
			NamespacedName: types.NamespacedName{
				Name:      gpr.Name,
				Namespace: gpr.Namespace,
			},
		})
	}
	return requests
}

func goldenPathRepoWatchesBlueprint(gpr *repavev1alpha1.GoldenPathRepo, blueprintName string) bool {
	if gpr.Spec.BlueprintRef != nil && gpr.Spec.BlueprintRef.Name == blueprintName {
		return true
	}
	return gpr.Spec.DesiredPins.BlueprintName == blueprintName
}

func blueprintWatchHandler(r *GoldenPathRepoReconciler) handler.EventHandler {
	return handler.EnqueueRequestsFromMapFunc(r.enqueueGoldenPathReposForBlueprint)
}
