package controller

import (
	"context"
	"path/filepath"
	"testing"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes/scheme"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/envtest"
	logf "sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
)

var (
	testEnv   *envtest.Environment
	k8sClient client.Client
)

func TestControllers(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Controller Suite")
}

var _ = BeforeSuite(func() {
	logf.SetLogger(zap.New(zap.WriteTo(GinkgoWriter), zap.UseDevMode(true)))

	By("bootstrapping test environment")
	testEnv = &envtest.Environment{
		CRDDirectoryPaths:     []string{filepath.Join("..", "..", "config", "crd", "bases")},
		ErrorIfCRDPathMissing: true,
	}

	cfg, err := testEnv.Start()
	Expect(err).NotTo(HaveOccurred())
	Expect(cfg).NotTo(BeNil())

	err = repavev1alpha1.AddToScheme(scheme.Scheme)
	Expect(err).NotTo(HaveOccurred())

	k8sClient, err = client.New(cfg, client.Options{Scheme: scheme.Scheme})
	Expect(err).NotTo(HaveOccurred())
})

var _ = AfterSuite(func() {
	By("tearing down the test environment")
	if testEnv != nil {
		Expect(testEnv.Stop()).To(Succeed())
	}
})

var _ = Describe("GoldenPathRepo controller", func() {
	const name = "test-gpr"

	ctx := context.Background()
	typeNamespacedName := types.NamespacedName{
		Name:      name,
		Namespace: "default",
	}

	BeforeEach(func() {
		repo := &repavev1alpha1.GoldenPathRepo{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: "default",
			},
			Spec: repavev1alpha1.GoldenPathRepoSpec{
				LocalPath: "/tmp/example-module",
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

	It("should accept CRD create and allow status subresource update", func() {
		repo := &repavev1alpha1.GoldenPathRepo{}
		Expect(k8sClient.Get(ctx, typeNamespacedName, repo)).To(Succeed())

		repo.Status.Phase = repavev1alpha1.GoldenPathRepoPhaseReady
		repo.Status.Message = "envtest"
		repo.Status.ObservedGeneration = repo.Generation
		Expect(k8sClient.Status().Update(ctx, repo)).To(Succeed())

		updated := &repavev1alpha1.GoldenPathRepo{}
		Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
		Expect(updated.Status.Phase).To(Equal(repavev1alpha1.GoldenPathRepoPhaseReady))
		Expect(updated.Status.Message).To(Equal("envtest"))
	})
})
