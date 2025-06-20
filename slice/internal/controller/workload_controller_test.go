/*
Copyright 2025.

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

package controller

import (
	"time"

	. "github.com/onsi/ginkgo/v2"
	"github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	"tpu-slice-controller/api/v1alpha1"
)

var _ = Describe("Workload Controller", func() {
	Context("When reconciling a resource", func() {
		var (
			ns *corev1.Namespace
			wl *kueue.Workload
		)

		BeforeEach(func() {
			ns = &corev1.Namespace{
				ObjectMeta: metav1.ObjectMeta{
					Name: "test-ns",
				},
			}
			gomega.Expect(k8sClient.Create(ctx, ns)).To(gomega.Succeed())

			wl = &kueue.Workload{
				ObjectMeta: metav1.ObjectMeta{Name: "test-wl", Namespace: ns.Name},
				Spec: kueue.WorkloadSpec{
					PodSets: []kueue.PodSet{
						{
							Name:  "main",
							Count: int32(1),
							Template: corev1.PodTemplateSpec{
								Spec: corev1.PodSpec{
									RestartPolicy: corev1.RestartPolicyNever,
									Containers: []corev1.Container{
										{
											Name: "c",
											Resources: corev1.ResourceRequirements{
												Requests: make(corev1.ResourceList),
											},
										},
									},
								},
							},
						},
					},
				},
			}

			gomega.Expect(k8sClient.Create(ctx, wl)).To(gomega.Succeed())
		})

		AfterEach(func() {
			gomega.Expect(k8sClient.Delete(ctx, wl)).To(gomega.Succeed())
			gomega.Expect(k8sClient.Delete(ctx, ns)).To(gomega.Succeed())
		})

		It("should successfully reconcile the resource", func() {
			By("Ensuring the controller adds the finalizer")
			gomega.Eventually(func(g gomega.Gomega) {
				updatedWl := &kueue.Workload{}
				err := k8sClient.Get(ctx, client.ObjectKeyFromObject(wl), updatedWl)
				g.Expect(err).ToNot(gomega.HaveOccurred())
				g.Expect(controllerutil.ContainsFinalizer(updatedWl, v1alpha1.CleanupSliceFinalizerName)).To(gomega.BeTrue())
			}, 10*time.Second, 250*time.Millisecond).Should(gomega.Succeed())

		})
	})
})
