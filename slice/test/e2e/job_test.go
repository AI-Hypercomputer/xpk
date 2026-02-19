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
	"github.com/google/go-cmp/cmp/cmpopts"
	"github.com/onsi/ginkgo/v2"
	"github.com/onsi/gomega"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/ptr"
	"sigs.k8s.io/controller-runtime/pkg/client"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta2"
	jobcontroller "sigs.k8s.io/kueue/pkg/controller/jobs/job"
	"sigs.k8s.io/kueue/pkg/util/tas"
	"sigs.k8s.io/kueue/pkg/workload"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/controller"
	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/util/testing"
	testingjobs "tpu-slice-controller/internal/util/testingjobs/job"
	"tpu-slice-controller/test/utils"
)

var _ = ginkgo.Describe("Job", func() {
	var (
		topology *kueue.Topology
		ns       *corev1.Namespace
		rf       *kueue.ResourceFlavor
		ac       *kueue.AdmissionCheck
		cq       *kueue.ClusterQueue
		lq       *kueue.LocalQueue
	)

	ginkgo.BeforeEach(func() {
		ns = testing.MakeNamespaceWithGenerateName("e2e-job-")
		utils.MustCreate(ctx, k8sClient, ns)

		topology = testing.MakeTopology("topology").
			Levels(core.TPUBlockLabel, core.TPUSubBlockLabel, "kubernetes.io/hostname").
			Obj()
		utils.MustCreate(ctx, k8sClient, topology)

		rf = testing.MakeResourceFlavor("rf").
			NodeLabel(nodeGroupLabel, nodeGroup).
			TopologyName(topology.Name).
			Obj()
		utils.MustCreate(ctx, k8sClient, rf)

		ac = testing.MakeAdmissionCheck("ac").ControllerName(controller.SliceControllerName).Obj()
		utils.MustCreate(ctx, k8sClient, ac)

		cq = testing.MakeClusterQueue("cq").
			AdmissionChecks(ac.Name).
			ResourceGroup(*testing.MakeFlavorQuotas(rf.Name).
				Resource(core.TPUResourceName, "9999").
				Obj()).
			Obj()
		utils.MustCreate(ctx, k8sClient, cq)

		lq = testing.MakeLocalQueue("lq", ns.Name).ClusterQueue(cq.Name).Obj()
		utils.MustCreate(ctx, k8sClient, lq)
	})

	ginkgo.AfterEach(func() {
		gomega.Expect(utils.DeleteNamespace(ctx, k8sClient, ns)).To(gomega.Succeed())
		utils.ExpectObjectToBeDeleted(ctx, k8sClient, cq, true)
		utils.ExpectObjectToBeDeleted(ctx, k8sClient, ac, true)
		utils.ExpectObjectToBeDeleted(ctx, k8sClient, rf, true)
		utils.ExpectObjectToBeDeleted(ctx, k8sClient, topology, true)
		utils.ExpectAllPodsInNamespaceDeleted(ctx, k8sClient, ns)
	})

	ginkgo.When("Creating a Job", func() {
		ginkgo.It("should create Slice based on created Workload", func() {
			job := testingjobs.MakeJob("job", ns.Name).
				Queue(lq.Name).
				Image(utils.E2eTestAgnHostImage).
				Args(utils.BehaviorWaitForDeletion...).
				Parallelism(16).
				Completions(16).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x4").
				NodeSelector(core.TPUAcceleratorLabel, string(slice.TypeTpu7x)).
				RequestAndLimit(core.TPUResourceName, "4").
				Obj()

			ginkgo.By("Creating a Job", func() {
				utils.MustCreate(ctx, k8sClient, job)
			})

			createdJob := &batchv1.Job{}

			ginkgo.By("Checking that the Job is created with annotations/selectors", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(job), createdJob)).To(gomega.Succeed())
					// annotations for 2-level TAS.
					annotations := createdJob.Spec.Template.Annotations
					g.Expect(annotations[kueue.PodSetRequiredTopologyAnnotation]).
						Should(gomega.Equal(core.TPUBlockLabel))
					g.Expect(annotations[kueue.PodSetSliceRequiredTopologyAnnotation]).
						Should(gomega.Equal(core.TPUSubBlockLabel))
					g.Expect(annotations[kueue.PodSetSliceSizeAnnotation]).
						Should(gomega.Equal("16"))

					// node health
					affinity := createdJob.Spec.Template.Spec.Affinity
					g.Expect(affinity).ShouldNot(gomega.BeNil())
					g.Expect(affinity.NodeAffinity).ShouldNot(gomega.BeNil())
					g.Expect(affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution).ShouldNot(gomega.BeNil())
					found := false
					for _, term := range affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms {
						for _, matchExpression := range term.MatchExpressions {
							if matchExpression.Key == core.TPUSliceHealthNodeSelectorKey {
								found = true
								g.Expect(matchExpression.Operator).Should(gomega.Equal(corev1.NodeSelectorOpIn))
								g.Expect(matchExpression.Values).Should(gomega.ConsistOf(core.TPUSliceHealthNodeSelectorHealthy))
							}
						}
					}
					g.Expect(found).Should(gomega.BeTrue())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			createdWorkload := &kueue.Workload{}
			wlKey := types.NamespacedName{
				Name:      jobcontroller.GetWorkloadNameForJob(job.Name, job.UID),
				Namespace: ns.Name,
			}

			ginkgo.By("Validating the Workload", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).To(gomega.Succeed())
					g.Expect(createdWorkload.Spec.PodSets).To(gomega.HaveLen(1))
					g.Expect(createdWorkload.Spec.PodSets[0].TopologyRequest).To(gomega.BeComparableTo(&kueue.PodSetTopologyRequest{
						Required:                    ptr.To(core.TPUBlockLabel),
						PodSetSliceRequiredTopology: ptr.To(core.TPUSubBlockLabel),
						PodSetSliceSize:             ptr.To[int32](16),
					}, ignorePodSetTopologyRequestFields))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Waiting for Admission of the Workload", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Verifying TopologyAssignment", func() {
				gomega.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments).Should(gomega.HaveLen(1))

				assignment := tas.InternalFrom(createdWorkload.Status.Admission.PodSetAssignments[0].TopologyAssignment)
				gomega.Expect(assignment.Levels).Should(gomega.Equal([]string{"kubernetes.io/hostname"}))
				gomega.Expect(assignment.Domains).Should(gomega.BeComparableTo([]tas.TopologyDomainAssignment{{
					Values: []string{"kind-worker"},
					Count:  16,
				}}))
			})

			createdSlice := &slice.Slice{}
			sliceKey := core.SliceKeyFromWorkload(createdWorkload, "main", 0)

			ginkgo.By("Checking that Slice is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					g.Expect(createdSlice.Spec.PartitionIds).To(gomega.HaveLen(1))
					g.Expect(createdSlice.Spec.PartitionIds).To(gomega.BeComparableTo([]string{"sb1"}))
					g.Expect(createdSlice.Spec.Topology).To(gomega.Equal("4x4x4"))
					g.Expect(createdSlice.Spec.Type).To(gomega.Equal(slice.TypeTpu7x))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Workload waiting for admission", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeFalse())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStatePending,
						Message: `Slices are in states: 1 CREATED`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding Ready condition", func() {
				utils.SetSliceReady(ctx, k8sClient, sliceKey, "4x4x4")
			})

			ginkgo.By("Checking that the Workload is admitted and admission check status is ready", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeTrue())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStateReady,
						Message: `Slices are in states: 1 ACTIVE`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
				}, utils.LongTimeout, utils.Timeout).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that pods are created and got the topology annotation", func() {
				pods := &corev1.PodList{}
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.List(ctx, pods, client.InNamespace(ns.Name))).To(gomega.Succeed())
					g.Expect(pods.Items).Should(gomega.HaveLen(16))
					for _, pod := range pods.Items {
						g.Expect(pod.Spec.NodeSelector).To(gomega.HaveKeyWithValue(core.TPUTopologyAnnotation, "4x4x4"))
					}
				}, utils.LongTimeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Deleting Job", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, job, true)
			})

			ginkgo.By("Checking that Slice is deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice, false)
			})

			ginkgo.By("Checking that all Pods are deleted", func() {
				utils.ExpectAllPodsInNamespaceDeleted(ctx, k8sClient, ns)
			})

			ginkgo.By("Checking that Workload is deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdWorkload, false)
			})
		})
	})
})
