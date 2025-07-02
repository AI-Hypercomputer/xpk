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
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueuealpha "sigs.k8s.io/kueue/apis/kueue/v1alpha1"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	jobsetcontroller "sigs.k8s.io/kueue/pkg/controller/jobs/jobset"

	slice "tpu-slice-controller/api/v1alpha1"
	"tpu-slice-controller/internal/controller"
	"tpu-slice-controller/internal/util/testing"
	testingjobsjobset "tpu-slice-controller/internal/util/testingjobs/jobset"
	"tpu-slice-controller/internal/webhooks"
	"tpu-slice-controller/test/utils"
)

var _ = ginkgo.Describe("JobSet", func() {
	var (
		topology *kueuealpha.Topology
		ns       *corev1.Namespace
		rf       *kueue.ResourceFlavor
		cq       *kueue.ClusterQueue
		lq       *kueue.LocalQueue
	)

	ginkgo.BeforeEach(func() {
		ns = testing.MakeNamespaceWithGenerateName("e2e-jobset-")
		utils.MustCreate(ctx, k8sClient, ns)

		topology = testing.MakeDefaultOneLevelTopology("hostname")
		utils.MustCreate(ctx, k8sClient, topology)

		rf = testing.MakeResourceFlavor("rf").
			NodeLabel("instance-type", "on-demand").
			TopologyName(topology.Name).
			Obj()
		utils.MustCreate(ctx, k8sClient, rf)

		cq = testing.MakeClusterQueue("cq").
			ResourceGroup(*testing.MakeFlavorQuotas(rf.Name).
				Resource(corev1.ResourceCPU, "2").
				Obj()).
			Obj()
		utils.MustCreate(ctx, k8sClient, cq)

		lq = testing.MakeLocalQueue("lq", ns.Name).ClusterQueue(cq.Name).Obj()
		utils.MustCreate(ctx, k8sClient, lq)
	})

	ginkgo.AfterEach(func() {
		gomega.Expect(utils.DeleteNamespace(ctx, k8sClient, ns)).To(gomega.Succeed())
		utils.ExpectObjectToBeDeleted(ctx, k8sClient, cq, true)
		utils.ExpectObjectToBeDeleted(ctx, k8sClient, rf, true)
		utils.ExpectObjectToBeDeleted(ctx, k8sClient, topology, true)
		utils.ExpectAllPodsInNamespaceDeleted(ctx, k8sClient, ns)
	})

	ginkgo.When("Creating a JobSet", func() {
		ginkgo.It("should create Slice based on created Workload", func() {
			jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
				Queue(lq.Name).
				ReplicatedJobs(
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj1",
						Image:       utils.E2eTestAgnHostImage,
						Args:        utils.BehaviorWaitForDeletion,
						Replicas:    1,
						Parallelism: 1,
						Completions: 1,
						PodAnnotations: map[string]string{
							kueuealpha.PodSetRequiredTopologyAnnotation: corev1.LabelHostname,
						},
					},
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj2",
						Image:       utils.E2eTestAgnHostImage,
						Args:        utils.BehaviorWaitForDeletion,
						Replicas:    1,
						Parallelism: 1,
						Completions: 1,
						PodAnnotations: map[string]string{
							kueuealpha.PodSetRequiredTopologyAnnotation: corev1.LabelHostname,
						},
					},
				).
				RequestAndLimit("rj1", "cpu", "200m").
				RequestAndLimit("rj2", "cpu", "200m").
				Obj()

			ginkgo.By("Creating the JobSet", func() {
				utils.MustCreate(ctx, k8sClient, jobSet)
			})

			createdJobSet := &jobset.JobSet{}

			ginkgo.By("Checking that JobSet is created with annotations", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(jobSet), createdJobSet)).To(gomega.Succeed())
					for _, replicatedJob := range createdJobSet.Spec.ReplicatedJobs {
						g.Expect(replicatedJob.Template.Annotations[webhooks.PodSetRequiredTopologyAnnotation]).Should(gomega.Equal(webhooks.AnnotationValueTBD))
						g.Expect(replicatedJob.Template.Annotations[webhooks.PodSetSliceRequiredTopologyAnnotation]).Should(gomega.Equal(webhooks.AnnotationValueTBD))
						g.Expect(replicatedJob.Template.Annotations[webhooks.PodSetSliceSizeAnnotation]).Should(gomega.Equal(webhooks.AnnotationValueTBD))
					}
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			createdWorkload := &kueue.Workload{}
			wlKey := types.NamespacedName{
				Name:      jobsetcontroller.GetWorkloadNameForJobSet(jobSet.Name, jobSet.UID),
				Namespace: ns.Name,
			}

			ginkgo.By("Waiting for admission of workload and verify TopologyAssignment", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
				gomega.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments).Should(gomega.HaveLen(2))
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments[0].TopologyAssignment).Should(gomega.BeComparableTo(
					&kueue.TopologyAssignment{
						Levels: []string{corev1.LabelHostname},
						Domains: []kueue.TopologyDomainAssignment{{
							Count:  1,
							Values: []string{"kind-worker"},
						}},
					},
				))
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments[1].TopologyAssignment).Should(gomega.BeComparableTo(
					&kueue.TopologyAssignment{
						Levels: []string{corev1.LabelHostname},
						Domains: []kueue.TopologyDomainAssignment{{
							Count:  1,
							Values: []string{"kind-worker"},
						}},
					},
				))
			})

			createdSlice := &slice.Slice{}
			sliceKey := types.NamespacedName{
				Name:      wlKey.Name,
				Namespace: wlKey.Namespace,
			}

			ginkgo.By("Checking that Slice is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					g.Expect(createdSlice.Spec.NodeSelector).To(gomega.HaveLen(1))
					g.Expect(createdSlice.Spec.NodeSelector).To(gomega.HaveKeyWithValue(
						controller.TPUReservationSubblockLabel, []string{"kind-worker"},
					))
				}, utils.LongTimeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Deleting JobSet", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, jobSet, true)
			})

			ginkgo.By("Checking that Slice is deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice, false)
			})
		})
	})
})
