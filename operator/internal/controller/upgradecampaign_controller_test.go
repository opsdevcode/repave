package controller

import (
	"context"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/campaign"
	"github.com/opsdevcode/repave/operator/internal/remediation"
)

var _ = Describe("UpgradeCampaign controller", func() {
	It("publishes drift SLO stats in status", func() {
		ctx := context.Background()
		driftStart := metav1.Now()
		uc := &repavev1beta1.UpgradeCampaign{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "fleet",
				Namespace: "default",
			},
			Spec: repavev1beta1.UpgradeCampaignSpec{},
		}
		Expect(k8sClient.Create(ctx, uc)).To(Succeed())

		gpr := &repavev1beta1.GoldenPathRepo{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "payments-api",
				Namespace: "default",
				Labels: map[string]string{
					campaign.UpgradeCampaignLabel: "fleet",
				},
			},
			Spec: repavev1beta1.GoldenPathRepoSpec{
				LocalPath: "/tmp/payments-api",
				DesiredPins: repavev1beta1.DesiredPins{
					BlueprintName:    "app-service-generic",
					BlueprintVersion: "1.0.0",
					StandardSource:   "standards/app-standards",
					StandardVersion:  "1.0.0",
				},
			},
		}
		Expect(k8sClient.Create(ctx, gpr)).To(Succeed())

		var persisted repavev1beta1.GoldenPathRepo
		Expect(k8sClient.Get(ctx, types.NamespacedName{Name: "payments-api", Namespace: "default"}, &persisted)).To(Succeed())
		persisted.Status.Phase = repavev1beta1.GoldenPathRepoPhaseOutOfDate
		persisted.Status.DriftDetectedAt = &driftStart
		persisted.Status.RemediationPR = &repavev1beta1.RemediationPRStatus{
			State: remediation.PRStateOpen,
		}
		Expect(k8sClient.Status().Update(ctx, &persisted)).To(Succeed())

		reconciler := &UpgradeCampaignReconciler{
			Client: k8sClient,
			Scheme: k8sClient.Scheme(),
		}
		_, err := reconciler.Reconcile(ctx, reconcile.Request{
			NamespacedName: types.NamespacedName{Name: "fleet", Namespace: "default"},
		})
		Expect(err).NotTo(HaveOccurred())

		var latest repavev1beta1.UpgradeCampaign
		Expect(k8sClient.Get(ctx, types.NamespacedName{Name: "fleet", Namespace: "default"}, &latest)).To(Succeed())
		Expect(latest.Status.OutOfDateCount).To(Equal(int32(1)))
		Expect(latest.Status.OpenPRCount).To(Equal(int32(1)))
		Expect(latest.Status.OldestDriftAgeSeconds).To(BeNumerically(">=", int64(0)))
		Expect(latest.Status.Phase).To(Equal(repavev1beta1.UpgradeCampaignPhaseActive))
	})
})
