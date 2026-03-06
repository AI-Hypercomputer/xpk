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

package e2e

import (
	"github.com/onsi/ginkgo/v2"
	"github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"

	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/util/testing"
	"tpu-slice-controller/test/utils"
)

var _ = ginkgo.Describe("Webhook Selector", func() {
	var ns *corev1.Namespace

	ginkgo.BeforeEach(func() {
		ns = testing.MakeNamespaceWithGenerateName("e2e-webhook-")
		utils.MustCreate(ctx, k8sClient, ns)
	})

	ginkgo.AfterEach(func() {
		gomega.Expect(utils.DeleteNamespace(ctx, k8sClient, ns)).To(gomega.Succeed())
	})

	ginkgo.It("should only process pods with the specific label", func() {
		// Define a pod with anti-affinity but WITHOUT the selector label.
		// The webhook should NOT intercept this pod, so anti-affinity should remain.
		podWithoutLabel := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "pod-without-label",
				Namespace: ns.Name,
			},
			Spec: corev1.PodSpec{
				RestartPolicy: corev1.RestartPolicyNever,
				Containers: []corev1.Container{
					{
						Name:  "pause",
						Image: utils.E2eTestAgnHostImage,
					},
				},
				Affinity: &corev1.Affinity{
					NodeAffinity: &corev1.NodeAffinity{
						RequiredDuringSchedulingIgnoredDuringExecution: &corev1.NodeSelector{
							NodeSelectorTerms: []corev1.NodeSelectorTerm{
								{
									MatchExpressions: []corev1.NodeSelectorRequirement{
										{
											Key:      core.TPUSliceNodeLabel,
											Operator: corev1.NodeSelectorOpDoesNotExist,
										},
									},
								},
							},
						},
					},
				},
			},
		}

		ginkgo.By("Creating a pod without the label", func() {
			utils.MustCreate(ctx, k8sClient, podWithoutLabel)
		})

		ginkgo.By("Verifying that anti-affinity is preserved (webhook did not run)", func() {
			createdPod := &corev1.Pod{}
			gomega.Eventually(func(g gomega.Gomega) {
				g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(podWithoutLabel), createdPod)).To(gomega.Succeed())
				req := core.FindNodeAffinityRequirement(&corev1.PodTemplateSpec{Spec: createdPod.Spec}, core.TPUSliceNodeLabel)
				g.Expect(req).NotTo(gomega.BeNil())
				g.Expect(req.Operator).To(gomega.Equal(corev1.NodeSelectorOpDoesNotExist))
			}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
		})

		// Define a pod with anti-affinity AND WITH the selector label.
		// The webhook SHOULD intercept this pod and remove the anti-affinity.
		podWithLabel := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "pod-with-label",
				Namespace: ns.Name,
				Labels: map[string]string{
					"cloud.google.com/gke-tpu-slice-pod": "true",
				},
			},
			Spec: corev1.PodSpec{
				RestartPolicy: corev1.RestartPolicyNever,
				Containers: []corev1.Container{
					{
						Name:  "pause",
						Image: utils.E2eTestAgnHostImage,
					},
				},
				Affinity: &corev1.Affinity{
					NodeAffinity: &corev1.NodeAffinity{
						RequiredDuringSchedulingIgnoredDuringExecution: &corev1.NodeSelector{
							NodeSelectorTerms: []corev1.NodeSelectorTerm{
								{
									MatchExpressions: []corev1.NodeSelectorRequirement{
										{
											Key:      core.TPUSliceNodeLabel,
											Operator: corev1.NodeSelectorOpDoesNotExist,
										},
									},
								},
							},
						},
					},
				},
			},
		}

		ginkgo.By("Creating a pod with the label", func() {
			utils.MustCreate(ctx, k8sClient, podWithLabel)
		})

		ginkgo.By("Verifying that anti-affinity is removed (webhook ran)", func() {
			createdPod := &corev1.Pod{}
			gomega.Eventually(func(g gomega.Gomega) {
				g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(podWithLabel), createdPod)).To(gomega.Succeed())
				g.Expect(createdPod.Spec.Affinity).To(gomega.BeNil())
			}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
		})
	})

	ginkgo.It("should remove anti-affinity but keep other match expressions", func() {
		podWithMultipleExpressions := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "pod-with-multiple-expressions",
				Namespace: ns.Name,
				Labels: map[string]string{
					"cloud.google.com/gke-tpu-slice-pod": "true",
				},
			},
			Spec: corev1.PodSpec{
				RestartPolicy: corev1.RestartPolicyNever,
				Containers: []corev1.Container{
					{
						Name:  "pause",
						Image: utils.E2eTestAgnHostImage,
					},
				},
				Affinity: &corev1.Affinity{
					NodeAffinity: &corev1.NodeAffinity{
						RequiredDuringSchedulingIgnoredDuringExecution: &corev1.NodeSelector{
							NodeSelectorTerms: []corev1.NodeSelectorTerm{
								{
									MatchExpressions: []corev1.NodeSelectorRequirement{
										{
											Key:      core.TPUSliceNodeLabel,
											Operator: corev1.NodeSelectorOpDoesNotExist,
										},
										{
											Key:      "other-key",
											Operator: corev1.NodeSelectorOpExists,
										},
									},
								},
							},
						},
					},
				},
			},
		}

		ginkgo.By("Creating a pod with multiple match expressions", func() {
			utils.MustCreate(ctx, k8sClient, podWithMultipleExpressions)
		})

		ginkgo.By("Verifying that anti-affinity is removed but other expression remains", func() {
			createdPod := &corev1.Pod{}
			gomega.Eventually(func(g gomega.Gomega) {
				g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(podWithMultipleExpressions), createdPod)).To(gomega.Succeed())
				g.Expect(createdPod.Spec.Affinity).NotTo(gomega.BeNil())
				req := core.FindNodeAffinityRequirement(&corev1.PodTemplateSpec{Spec: createdPod.Spec}, core.TPUSliceNodeLabel)
				g.Expect(req).To(gomega.BeNil())
				reqOther := core.FindNodeAffinityRequirement(&corev1.PodTemplateSpec{Spec: createdPod.Spec}, "other-key")
				g.Expect(reqOther).NotTo(gomega.BeNil())
				g.Expect(reqOther.Operator).To(gomega.Equal(corev1.NodeSelectorOpExists))
			}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
		})
	})
})
