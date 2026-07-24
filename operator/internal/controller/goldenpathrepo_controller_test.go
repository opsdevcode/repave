package controller

import (
	"context"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes/scheme"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/status"
)

var _ = Describe("GoldenPathRepo reconciler", func() {
	const name = "reconcile-gpr"

	ctx := context.Background()
	typeNamespacedName := types.NamespacedName{Name: name, Namespace: "default"}

	var reconciler *GoldenPathRepoReconciler

	BeforeEach(func() {
		reconciler = &GoldenPathRepoReconciler{
			Client: k8sClient,
			Scheme: scheme.Scheme,
		}
		repo := &repavev1alpha1.GoldenPathRepo{
			ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: "default"},
			Spec: repavev1alpha1.GoldenPathRepoSpec{
				LocalPath: "/tmp/reconcile-fixture",
				DesiredPins: repavev1alpha1.DesiredPins{
					BlueprintName:    "terraform-module-generic",
					BlueprintVersion: "0.1.0",
					StandardSource:   "examples/standards",
					StandardVersion:  "0.4.0",
				},
			},
		}
		Expect(k8sClient.Create(ctx, repo)).To(Succeed())
	})

	AfterEach(func() {
		repo := &repavev1alpha1.GoldenPathRepo{}
		Expect(k8sClient.Get(ctx, typeNamespacedName, repo)).To(Succeed())
		Expect(k8sClient.Delete(ctx, repo)).To(Succeed())
	})

	It("sets Ready status on reconcile", func() {
		_, err := reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
		Expect(err).NotTo(HaveOccurred())

		repo := &repavev1alpha1.GoldenPathRepo{}
		Expect(k8sClient.Get(ctx, typeNamespacedName, repo)).To(Succeed())
		Expect(repo.Status.Phase).To(Equal(repavev1alpha1.GoldenPathRepoPhaseReady))
		Expect(repo.Status.ObservedGeneration).To(Equal(repo.Generation))
		Expect(repo.Status.Message).To(ContainSubstring("operator scaffold"))
		Expect(meta.IsStatusConditionTrue(repo.Status.Conditions, status.ConditionReady)).To(BeTrue())
	})

	It("sets Error when neither repoURL nor localPath is set", func() {
		repo := &repavev1alpha1.GoldenPathRepo{}
		Expect(k8sClient.Get(ctx, typeNamespacedName, repo)).To(Succeed())
		repo.Spec.LocalPath = ""
		Expect(k8sClient.Update(ctx, repo)).NotTo(Succeed())
	})
})
