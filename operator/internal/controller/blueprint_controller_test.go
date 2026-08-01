package controller

import (
	"context"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
)

var _ = Describe("Blueprint controller", func() {
	It("publishes target pins in status", func() {
		ctx := context.Background()
		name := "bp-target"
		bp := &repavev1beta1.Blueprint{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: "default",
			},
			Spec: repavev1beta1.BlueprintSpec{
				Version: "1.2.3",
				Standard: repavev1beta1.BlueprintStandardPins{
					Source:  "standards/terraform-standards",
					Version: "1.1.0",
				},
			},
		}
		Expect(k8sClient.Create(ctx, bp)).To(Succeed())

		reconciler := &BlueprintReconciler{
			Client: k8sClient,
			Scheme: k8sClient.Scheme(),
		}
		_, err := reconciler.Reconcile(ctx, reconcile.Request{
			NamespacedName: types.NamespacedName{Name: name, Namespace: "default"},
		})
		Expect(err).NotTo(HaveOccurred())

		var latest repavev1beta1.Blueprint
		Expect(k8sClient.Get(ctx, types.NamespacedName{Name: name, Namespace: "default"}, &latest)).To(Succeed())
		Expect(latest.Status.TargetPins).NotTo(BeNil())
		Expect(latest.Status.TargetPins.Version).To(Equal("1.2.3"))
		Expect(latest.Status.TargetPins.StandardVersion).To(Equal("1.1.0"))
	})
})
