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
	_ context.Context,
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
	return []reconcile.Request{{
		NamespacedName: types.NamespacedName{
			Name:      campaignName,
			Namespace: gpr.Namespace,
		},
	}}
}

func upgradeCampaignWatchHandler(r *UpgradeCampaignReconciler) handler.EventHandler {
	return handler.EnqueueRequestsFromMapFunc(r.enqueueUpgradeCampaignsForGoldenPathRepo)
}
