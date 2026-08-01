package controller

import (
	"context"

	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/handler"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/campaign"
)

func (r *UpgradeCampaignReconciler) enqueueUpgradeCampaignsForGoldenPathRepo(
	ctx context.Context,
	obj client.Object,
) []reconcile.Request {
	gpr, ok := obj.(*repavev1beta1.GoldenPathRepo)
	if !ok {
		return nil
	}
	campaignName := gpr.Labels[campaign.UpgradeCampaignLabel]
	if campaignName == "" {
		return nil
	}

	var list repavev1beta1.UpgradeCampaignList
	if err := r.List(ctx, &list, client.InNamespace(gpr.Namespace)); err != nil {
		return nil
	}

	requests := make([]reconcile.Request, 0, 1)
	for i := range list.Items {
		uc := &list.Items[i]
		if uc.Name != campaignName {
			continue
		}
		requests = append(requests, reconcile.Request{
			NamespacedName: types.NamespacedName{
				Name:      uc.Name,
				Namespace: uc.Namespace,
			},
		})
	}
	return requests
}

func upgradeCampaignWatchHandler(r *UpgradeCampaignReconciler) handler.EventHandler {
	return handler.EnqueueRequestsFromMapFunc(r.enqueueUpgradeCampaignsForGoldenPathRepo)
}
