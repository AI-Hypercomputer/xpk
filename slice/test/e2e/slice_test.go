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
	"k8s.io/utils/ptr"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueuealpha "sigs.k8s.io/kueue/apis/kueue/v1alpha1"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	jobcontroller "sigs.k8s.io/kueue/pkg/controller/jobs/job"
	jobsetcontroller "sigs.k8s.io/kueue/pkg/controller/jobs/jobset"
	"sigs.k8s.io/kueue/test/util"

	slice "tpu-slice-controller/api/v1alpha1"
	"tpu-slice-controller/internal/controller"
	"tpu-slice-controller/internal/util/testing"
	testingjobsjob "tpu-slice-controller/internal/util/testingjobs/job"
	testingjobsjobset "tpu-slice-controller/internal/util/testingjobs/jobset"
	"tpu-slice-controller/internal/webhooks"
	"tpu-slice-controller/test/utils"
)

var _ = ginkgo.Describe("Slice", func() {
	var (
		topology *kueuealpha.Topology
		ns       *corev1.Namespace
		rf       *kueue.ResourceFlavor
		cq       *kueue.ClusterQueue
		lq       *kueue.LocalQueue
	)

	ginkgo.BeforeEach(func() {
		ns = testing.MakeNamespaceWithGenerateName("e2e-slice-")
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

	ginkgo.When("Creating a Job", func() {
		ginkgo.It("shouldn't create Slice", func() {
			job := testingjobsjob.MakeJob("test-job", ns.Name).
				Queue(kueue.LocalQueueName(lq.Name)).
				Parallelism(3).
				Completions(3).
				RequestAndLimit(corev1.ResourceCPU, "200m").
				PodAnnotation(kueuealpha.PodSetRequiredTopologyAnnotation, corev1.LabelHostname).
				Image(util.E2eTestAgnHostImage, util.BehaviorWaitForDeletion).
				Obj()

			ginkgo.By("Creating the Job", func() {
				util.MustCreate(ctx, k8sClient, job)
			})

			createdWorkload := &kueue.Workload{}
			wlKey := types.NamespacedName{
				Name:      jobcontroller.GetWorkloadNameForJob(job.Name, job.UID),
				Namespace: ns.Name,
			}

			ginkgo.By("Waiting for admission of workload and verify TopologyAssignment", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())

				gomega.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments).Should(gomega.HaveLen(1))
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments[0].TopologyAssignment).Should(gomega.BeComparableTo(
					&kueue.TopologyAssignment{
						Levels: []string{corev1.LabelHostname},
						Domains: []kueue.TopologyDomainAssignment{{
							Count:  3,
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

			gomega.Consistently(func(g gomega.Gomega) {
				g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(testing.BeNotFoundError())
			}, utils.ConsistentDuration, utils.ShortInterval).Should(gomega.Succeed())
		})
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
				RequestAndLimit("rj1", corev1.ResourceCPU, "200m").
				RequestAndLimit("rj2", corev1.ResourceCPU, "200m").
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

		ginkgo.It("should delete Slice after all pods gracefully terminated", func() {
			jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
				Queue(lq.Name).
				ReplicatedJobs(
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj",
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
				RequestAndLimit("rj", corev1.ResourceCPU, "200m").
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
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments).Should(gomega.HaveLen(1))
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments[0].TopologyAssignment).Should(gomega.BeComparableTo(
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

			opts := []client.ListOption{
				client.InNamespace(jobSet.Namespace),
				client.MatchingLabels{jobset.JobSetNameKey: jobSet.Name},
			}
			addTestFinalizerForPods(opts)
			defer removeTestFinalizerFromPods(opts)

			ginkgo.By("Deactivating the Workload", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					createdWorkload.Spec.Active = ptr.To(false)
					g.Expect(k8sClient.Update(ctx, createdWorkload)).Should(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Slice still exists", func() {
				gomega.Consistently(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
				}, utils.ConsistentDuration, utils.ShortInterval).Should(gomega.Succeed())
			})

			removeTestFinalizerFromPods(opts)

			ginkgo.By("Checking that Slice is deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice, false)
			})
		})

		ginkgo.It("should delete the Slice after the JobSet is deleted", func() {
			jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
				Queue(lq.Name).
				ReplicatedJobs(
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj",
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
				RequestAndLimit("rj", corev1.ResourceCPU, "200m").
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
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments).Should(gomega.HaveLen(1))
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments[0].TopologyAssignment).Should(gomega.BeComparableTo(
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

			opts := []client.ListOption{
				client.InNamespace(jobSet.Namespace),
				client.MatchingLabels{jobset.JobSetNameKey: jobSet.Name},
			}
			addTestFinalizerForPods(opts)
			defer removeTestFinalizerFromPods(opts)

			ginkgo.By("Deactivating the Workload", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					createdWorkload.Spec.Active = ptr.To(false)
					g.Expect(k8sClient.Update(ctx, createdWorkload)).Should(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Slice still exists", func() {
				gomega.Consistently(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
				}, utils.ConsistentDuration, utils.ShortInterval).Should(gomega.Succeed())
			})

			ginkgo.By("Deleting the JobSet", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, jobSet, true)
			})

			ginkgo.By("Checking that Slice is deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice, false)
			})
		})
	})
})

func addTestFinalizerForPods(opts []client.ListOption) {
	pods := &corev1.PodList{}
	ginkgo.By("Adding test finalizer to Pods", func() {
		gomega.Eventually(func(g gomega.Gomega) {
			g.Expect(k8sClient.List(ctx, pods, opts...)).To(gomega.Succeed())
			for _, pod := range pods.Items {
				if controllerutil.AddFinalizer(&pod, controller.CleanupSliceFinalizerName) {
					g.Expect(k8sClient.Update(ctx, &pod)).To(gomega.Succeed())
				}
			}
		}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
	})
}

func removeTestFinalizerFromPods(opts []client.ListOption) {
	pods := &corev1.PodList{}
	ginkgo.By("Removing test finalizer from Pods", func() {
		gomega.Eventually(func(g gomega.Gomega) {
			g.Expect(k8sClient.List(ctx, pods, opts...)).To(gomega.Succeed())
			for _, pod := range pods.Items {
				if controllerutil.RemoveFinalizer(&pod, controller.CleanupSliceFinalizerName) {
					g.Expect(k8sClient.Update(ctx, &pod)).To(gomega.Succeed())
				}
			}
		}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
	})
}
