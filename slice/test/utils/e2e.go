/*
Copyright The Kubernetes Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package utils

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/google/go-cmp/cmp/cmpopts"
	"github.com/onsi/ginkgo/v2"
	"github.com/onsi/gomega"
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/config"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueuealpha "sigs.k8s.io/kueue/apis/kueue/v1alpha1"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/core"
)

const (
	// E2eTestAgnHostImage is the image used for testing.
	E2eTestAgnHostImage = "registry.k8s.io/e2e-test-images/agnhost:2.53"
)

func CreateClientUsingCluster(kContext string) (client.WithWatch, *rest.Config) {
	cfg, err := config.GetConfigWithContext(kContext)
	if err != nil {
		fmt.Printf("unable to get kubeconfig for context %q: %s", kContext, err)
		os.Exit(1)
	}
	gomega.ExpectWithOffset(1, cfg).NotTo(gomega.BeNil())

	err = slice.AddToScheme(scheme.Scheme)
	gomega.ExpectWithOffset(1, err).NotTo(gomega.HaveOccurred())

	err = kueue.AddToScheme(scheme.Scheme)
	gomega.ExpectWithOffset(1, err).NotTo(gomega.HaveOccurred())

	err = kueuealpha.AddToScheme(scheme.Scheme)
	gomega.ExpectWithOffset(1, err).NotTo(gomega.HaveOccurred())

	err = jobset.AddToScheme(scheme.Scheme)
	gomega.ExpectWithOffset(1, err).NotTo(gomega.HaveOccurred())

	client, err := client.NewWithWatch(cfg, client.Options{Scheme: scheme.Scheme})
	gomega.ExpectWithOffset(1, err).NotTo(gomega.HaveOccurred())

	return client, cfg
}

func WaitForSliceAvailability(ctx context.Context, k8sClient client.Client) {
	kcmKey := types.NamespacedName{Namespace: GetSliceNamespace(), Name: DefaultControllerManagerName}
	waitForOperatorAvailability(ctx, k8sClient, kcmKey)
}

func WaitForKueueAvailability(ctx context.Context, k8sClient client.Client) {
	jcmKey := types.NamespacedName{Namespace: "kueue-system", Name: "kueue-controller-manager"}
	waitForOperatorAvailability(ctx, k8sClient, jcmKey)
}

func WaitForJobSetAvailability(ctx context.Context, k8sClient client.Client) {
	jcmKey := types.NamespacedName{Namespace: "jobset-system", Name: "jobset-controller-manager"}
	waitForOperatorAvailability(ctx, k8sClient, jcmKey)
}

func waitForOperatorAvailability(ctx context.Context, k8sClient client.Client, key types.NamespacedName) {
	deployment := &appsv1.Deployment{}
	pods := &corev1.PodList{}
	waitForAvailableStart := time.Now()
	ginkgo.By(fmt.Sprintf("Waiting for availability of deployment: %q", key))
	gomega.EventuallyWithOffset(2, func(g gomega.Gomega) error {
		g.Expect(k8sClient.Get(ctx, key, deployment)).To(gomega.Succeed())
		g.Expect(k8sClient.List(ctx, pods, client.InNamespace(key.Namespace), client.MatchingLabels(deployment.Spec.Selector.MatchLabels))).To(gomega.Succeed())
		for _, pod := range pods.Items {
			for _, cs := range pod.Status.ContainerStatuses {
				// To make sure that we don't have restarts of controller-manager.
				// If we have that's mean that something went wrong, and there is
				// no needs to continue trying check availability.
				if cs.RestartCount > 0 {
					return gomega.StopTrying(fmt.Sprintf("%q in %q has restarted %d times", cs.Name, pod.Name, cs.RestartCount))
				}
			}
		}
		// To verify that webhooks are ready, checking is deployment have condition Available=True.
		g.Expect(deployment.Status.Conditions).To(gomega.ContainElement(gomega.BeComparableTo(
			appsv1.DeploymentCondition{Type: appsv1.DeploymentAvailable, Status: corev1.ConditionTrue},
			cmpopts.IgnoreFields(appsv1.DeploymentCondition{}, "Reason", "Message", "LastUpdateTime", "LastTransitionTime")),
		))
		return nil
	}, StartUpTimeout, Interval).Should(gomega.Succeed())
	ginkgo.GinkgoLogr.Info("Deployment is available in the cluster", "deployment", key, "waitingTime", time.Since(waitForAvailableStart))
}

func AnnotateNodesWithTopology(ctx context.Context, k8sClient client.Client, topology string) {
	nodes := &corev1.NodeList{}
	gomega.Expect(k8sClient.List(ctx, nodes)).To(gomega.Succeed())
	for _, node := range nodes.Items {
		gomega.Eventually(func(g gomega.Gomega) {
			n := &corev1.Node{}
			g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(&node), n)).To(gomega.Succeed())
			if n.Labels == nil {
				n.Labels = make(map[string]string)
			}
			n.Labels[core.TPUTopologyAnnotation] = topology
			g.Expect(k8sClient.Update(ctx, n)).To(gomega.Succeed())
		}, Timeout, Interval).Should(gomega.Succeed())
	}
}

func SetSliceReady(ctx context.Context, k8sClient client.Client, sliceKey client.ObjectKey, topology string) {
	createdSlice := &slice.Slice{}
	gomega.Eventually(func(g gomega.Gomega) {
		g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
		meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
			Type:    slice.SliceStateConditionType,
			Status:  metav1.ConditionTrue,
			Reason:  string(core.MMIGHealthStatusActive),
			Message: "Test",
		})
		g.Expect(k8sClient.Status().Update(ctx, createdSlice)).To(gomega.Succeed())
	}, Timeout, Interval).Should(gomega.Succeed())
	AnnotateNodesWithTopology(ctx, k8sClient, topology)
}
