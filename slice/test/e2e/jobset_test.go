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
	"fmt"
	"strconv"
	"time"

	"github.com/google/go-cmp/cmp/cmpopts"
	"github.com/onsi/ginkgo/v2"
	"github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/ptr"
	"sigs.k8s.io/controller-runtime/pkg/client"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta2"
	jobsetcontroller "sigs.k8s.io/kueue/pkg/controller/jobs/jobset"
	"sigs.k8s.io/kueue/pkg/util/tas"
	"sigs.k8s.io/kueue/pkg/workload"
	"sigs.k8s.io/kueue/test/util"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/controller"
	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/util/testing"
	testingjobsjobset "tpu-slice-controller/internal/util/testingjobs/jobset"
	"tpu-slice-controller/test/utils"
)

var (
	ignorePodSetTopologyRequestFields = cmpopts.IgnoreFields(kueue.PodSetTopologyRequest{}, "PodIndexLabel", "SubGroupIndexLabel")
)

var _ = ginkgo.Describe("JobSet", func() {
	var (
		topology *kueue.Topology
		ns       *corev1.Namespace
		rf       *kueue.ResourceFlavor
		ac       *kueue.AdmissionCheck
		cq       *kueue.ClusterQueue
		lq       *kueue.LocalQueue
	)

	ginkgo.BeforeEach(func() {
		ns = testing.MakeNamespaceWithGenerateName("e2e-jobset-")
		utils.MustCreate(ctx, k8sClient, ns)

		topology = testing.MakeTopology("topology").
			Levels("cloud.google.com/gce-topology-block", core.TPUSubBlockLabel, "kubernetes.io/hostname").
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

	ginkgo.When("Creating a JobSet", func() {
		type testCase struct {
			tpuTopology      string
			parallelism      int32
			replicas         int32
			wantSliceSize    int32
			tpuRequests      string
			unhealthyNodes   []string
			wantDomains      []tas.TopologyDomainAssignment
			wantPartitionIDs []string
			useNodeAffinity  bool
		}
		ginkgo.DescribeTable("it should create Slice based on created Workload with",
			func(tc testCase) {
				for _, unhealthyNode := range tc.unhealthyNodes {
					node := &corev1.Node{}
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: unhealthyNode}, node)).To(gomega.Succeed())
						delete(node.Labels, core.TPUSliceHealthNodeSelectorKey)
						g.Expect(k8sClient.Update(ctx, node)).To(gomega.Succeed())
					}, util.Timeout, util.Interval).Should(gomega.Succeed())
				}
				// Revert changes after test
				ginkgo.DeferCleanup(func() {
					for _, unhealthyNode := range tc.unhealthyNodes {
						node := &corev1.Node{}
						gomega.Eventually(func(g gomega.Gomega) {
							g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: unhealthyNode}, node)).To(gomega.Succeed())
							node.Labels[core.TPUSliceHealthNodeSelectorKey] = core.TPUSliceHealthNodeSelectorHealthy
							g.Expect(k8sClient.Update(ctx, node)).To(gomega.Succeed())
						}, util.Timeout, util.Interval).Should(gomega.Succeed())
					}
				})

				nodeSelector := map[string]string{
					"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
				}
				var affinity *corev1.Affinity
				if tc.useNodeAffinity {
					nodeSelector = nil
					affinity = core.TpuAffinity.DeepCopy()
				}

				jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
					Queue(lq.Name).
					ReplicatedJobs(
						testingjobsjobset.ReplicatedJobRequirements{
							Name:        "rj1",
							Image:       utils.E2eTestAgnHostImage,
							Args:        utils.BehaviorWaitForDeletion,
							Replicas:    tc.replicas,
							Parallelism: tc.parallelism,
							Completions: tc.parallelism,
							PodAnnotations: map[string]string{
								core.TPUSliceTopologyAnnotation: tc.tpuTopology,
							},
							NodeSelector: nodeSelector,
							Affinity:     affinity,
						},
					).
					RequestAndLimit("rj1", core.TPUResourceName, tc.tpuRequests).
					FailurePolicy(&jobset.FailurePolicy{
						MaxRestarts: 0,
					}).
					Obj()

				ginkgo.By("Creating a JobSet", func() {
					utils.MustCreate(ctx, k8sClient, jobSet)
				})

				createdJobSet := &jobset.JobSet{}

				ginkgo.By("Checking that the JobSet is created with annotations/selectors", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(jobSet), createdJobSet)).To(gomega.Succeed())
						for _, replicatedJob := range createdJobSet.Spec.ReplicatedJobs {
							// annotations for 2-level TAS.
							annotations := replicatedJob.Template.Spec.Template.Annotations
							g.Expect(annotations["kueue.x-k8s.io/podset-required-topology"]).
								Should(gomega.Equal("cloud.google.com/gce-topology-block"))
							g.Expect(annotations["kueue.x-k8s.io/podset-slice-required-topology"]).
								Should(gomega.Equal(core.TPUSubBlockLabel))
							g.Expect(annotations["kueue.x-k8s.io/podset-slice-size"]).
								Should(gomega.Equal(fmt.Sprint(tc.wantSliceSize)))

							// node health
							affinity := replicatedJob.Template.Spec.Template.Spec.Affinity
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
						}
					}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
				})

				createdWorkload := &kueue.Workload{}
				wlKey := types.NamespacedName{
					Name:      jobsetcontroller.GetWorkloadNameForJobSet(jobSet.Name, jobSet.UID),
					Namespace: ns.Name,
				}

				ginkgo.By("Validating the Workload", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).To(gomega.Succeed())
						g.Expect(createdWorkload.Spec.PodSets).To(gomega.HaveLen(1))
						g.Expect(createdWorkload.Spec.PodSets[0].TopologyRequest).To(gomega.BeComparableTo(&kueue.PodSetTopologyRequest{
							Required:                    ptr.To("cloud.google.com/gce-topology-block"),
							PodSetSliceRequiredTopology: ptr.To(core.TPUSubBlockLabel),
							SubGroupCount:               ptr.To(tc.replicas),
							PodSetSliceSize:             ptr.To(tc.wantSliceSize),
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
					gomega.Expect(assignment.Domains).Should(gomega.BeComparableTo(tc.wantDomains))
				})
				createdSlice := &slice.Slice{}
				sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1", 0)

				ginkgo.By("Checking that Slice is created", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
						g.Expect(createdSlice.Spec.PartitionIds).To(gomega.HaveLen(len(tc.wantPartitionIDs)))
						g.Expect(createdSlice.Spec.PartitionIds).To(gomega.BeComparableTo(tc.wantPartitionIDs))
						g.Expect(createdSlice.Spec.Topology).To(gomega.Equal(tc.tpuTopology))
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

				ginkgo.By("Adding Forming condition", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
						meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
							Type:    slice.SliceStateConditionType,
							Status:  metav1.ConditionFalse,
							Reason:  string(core.MMIGHealthStatusActivating),
							Message: "Test",
						})
						g.Expect(k8sClient.Status().Update(ctx, createdSlice)).To(gomega.Succeed())
					}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
				})

				ginkgo.By("Checking that the Workload still waiting for admission", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
						g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeFalse())
						g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
							Name:    kueue.AdmissionCheckReference(ac.Name),
							State:   kueue.CheckStatePending,
							Message: `Slices are in states: 1 ACTIVATING`,
						}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
					}, utils.LongTimeout, utils.Interval).Should(gomega.Succeed())
				})

				ginkgo.By("Adding Ready condition", func() {
					utils.SetSliceReady(ctx, k8sClient, sliceKey, tc.tpuTopology)
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

				ginkgo.By("Checking that all pods are running", func() {
					pods := &corev1.PodList{}
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.List(ctx, pods, client.InNamespace(ns.Name))).To(gomega.Succeed())
						g.Expect(pods.Items).Should(gomega.HaveLen(int(tc.parallelism)))
						for _, pod := range pods.Items {
							g.Expect(pod.Status.Phase).To(gomega.Equal(corev1.PodRunning))
							g.Expect(pod.Spec.NodeSelector).To(gomega.HaveKeyWithValue(core.TPUTopologyAnnotation, tc.tpuTopology))
						}
					}, utils.LongTimeout, utils.Interval).Should(gomega.Succeed())
				})

				ginkgo.By("Deleting JobSet", func() {
					utils.ExpectObjectToBeDeleted(ctx, k8sClient, jobSet, true)
				})

				ginkgo.By("Checking that Slice is deleted", func() {
					utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice, false)
				})

				ginkgo.By("Checking that Workload is deleted", func() {
					utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdWorkload, false)
				})
			},
			ginkgo.Entry("TPU topology 4x4x4, TPU topology 4 and parallelism 16", testCase{
				tpuTopology:   "4x4x4",
				tpuRequests:   "4",
				parallelism:   16,
				replicas:      1,
				wantSliceSize: 16,
				wantDomains: []tas.TopologyDomainAssignment{{
					Values: []string{"kind-worker"},
					Count:  16,
				}},
				wantPartitionIDs: []string{"sb1"},
			}),
			ginkgo.Entry("TPU topology 4x4x4, TPU topology 4 and parallelism 16 (missed kind-worker node)", testCase{
				tpuTopology:    "4x4x4",
				tpuRequests:    "4",
				parallelism:    16,
				replicas:       1,
				unhealthyNodes: []string{"kind-worker"},
				wantSliceSize:  16,
				wantDomains: []tas.TopologyDomainAssignment{{
					Values: []string{"kind-worker2"},
					Count:  16,
				}},
				wantPartitionIDs: []string{"sb2"},
			}),
			ginkgo.Entry("TPU topology, TPU topology 1 4x4x4 and parallelism 16", testCase{
				tpuTopology:   "4x4x4",
				tpuRequests:   "1",
				parallelism:   64,
				replicas:      1,
				wantSliceSize: 64,
				wantDomains: []tas.TopologyDomainAssignment{{
					Values: []string{"kind-worker"},
					Count:  64,
				}},
				wantPartitionIDs: []string{"sb1"},
			}),
			ginkgo.Entry("TPU topology 4x4x12 and parallelism 48", testCase{
				tpuTopology:   "4x4x12",
				tpuRequests:   "4",
				parallelism:   48,
				replicas:      1,
				wantSliceSize: 16,
				wantDomains: []tas.TopologyDomainAssignment{
					{
						Values: []string{"kind-worker2"},
						Count:  16,
					},
					{
						Values: []string{"kind-worker3"},
						Count:  16,
					},
					{
						Values: []string{"kind-worker4"},
						Count:  16,
					},
				},
				wantPartitionIDs: []string{"sb2", "sb3", "sb4"},
			}),
			ginkgo.Entry("TPU topology 4x4x12 and parallelism 96", testCase{
				tpuTopology:   "4x4x12",
				tpuRequests:   "2",
				parallelism:   96,
				replicas:      1,
				wantSliceSize: 32,
				wantDomains: []tas.TopologyDomainAssignment{
					{
						Values: []string{"kind-worker2"},
						Count:  32,
					},
					{
						Values: []string{"kind-worker3"},
						Count:  32,
					},
					{
						Values: []string{"kind-worker4"},
						Count:  32,
					},
				},
				wantPartitionIDs: []string{"sb2", "sb3", "sb4"},
			}),
			ginkgo.Entry("TPU topology 4x4x8 and parallelism 128", testCase{
				tpuTopology:   "4x4x8",
				tpuRequests:   "1",
				parallelism:   128,
				replicas:      1,
				wantSliceSize: 64,
				wantDomains: []tas.TopologyDomainAssignment{
					{
						Values: []string{"kind-worker2"},
						Count:  64,
					},
					{
						Values: []string{"kind-worker3"},
						Count:  64,
					},
				},
				wantPartitionIDs: []string{"sb2", "sb3"},
			}),
			ginkgo.Entry("TPU topology 4x4x4 with accelerator in NodeAffinity", testCase{
				tpuTopology:      "4x4x4",
				tpuRequests:      "4",
				parallelism:      16,
				replicas:         1,
				wantSliceSize:    16,
				wantDomains:      []tas.TopologyDomainAssignment{{Values: []string{"kind-worker"}, Count: 16}},
				wantPartitionIDs: []string{"sb1"},
				useNodeAffinity:  true,
			}),
		)

		ginkgo.Describe("it should create multiple Slices for multiple replicas", func() {
			type testCase struct {
				tpuTopology      string
				parallelism      int32
				replicas         int32
				wantSliceSize    int32
				tpuRequests      string
				wantDomains      []tas.TopologyDomainAssignment
				wantPartitionIDs [][]string
			}
			ginkgo.DescribeTable("with", func(tc testCase) {
				jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
					Queue(lq.Name).
					ReplicatedJobs(
						testingjobsjobset.ReplicatedJobRequirements{
							Name:        "rj1",
							Image:       utils.E2eTestAgnHostImage,
							Args:        utils.BehaviorWaitForDeletion,
							Replicas:    tc.replicas,
							Parallelism: tc.parallelism,
							Completions: tc.parallelism,
							PodAnnotations: map[string]string{
								core.TPUSliceTopologyAnnotation: tc.tpuTopology,
							},
							NodeSelector: map[string]string{
								"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
							},
						},
					).
					RequestAndLimit("rj1", core.TPUResourceName, tc.tpuRequests).
					Obj()

				ginkgo.By("Creating a JobSet", func() {
					utils.MustCreate(ctx, k8sClient, jobSet)
				})

				createdWorkload := &kueue.Workload{}
				wlKey := types.NamespacedName{
					Name:      jobsetcontroller.GetWorkloadNameForJobSet(jobSet.Name, jobSet.UID),
					Namespace: ns.Name,
				}
				createdSlices := make([]*slice.Slice, tc.replicas)

				ginkgo.By("Waiting for Admission of the Workload", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
						g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
					}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
				})

				for i := int32(0); i < tc.replicas; i++ {
					createdSlice := &slice.Slice{}
					sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1", i)

					ginkgo.By(fmt.Sprintf("Checking that Slice %d is created", i), func() {
						gomega.Eventually(func(g gomega.Gomega) {
							g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
							g.Expect(createdSlice.Spec.PartitionIds).To(gomega.HaveLen(len(tc.wantPartitionIDs[i])))
							g.Expect(createdSlice.Spec.PartitionIds).To(gomega.BeComparableTo(tc.wantPartitionIDs[i]))
							g.Expect(createdSlice.Spec.Topology).To(gomega.Equal(tc.tpuTopology))
							g.Expect(createdSlice.Spec.Type).To(gomega.Equal(slice.TypeTpu7x))
							createdSlices[i] = createdSlice
						}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
					})
				}

				for i := int32(0); i < tc.replicas; i++ {
					sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1", i)
					ginkgo.By(fmt.Sprintf("Adding Ready condition for slice %d", i), func() {
						utils.SetSliceReady(ctx, k8sClient, sliceKey, tc.tpuTopology)
					})
				}

				ginkgo.By("Checking that the Workload is admitted and admission check status is ready", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
						g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeTrue())
						g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
							Name:    kueue.AdmissionCheckReference(ac.Name),
							State:   kueue.CheckStateReady,
							Message: fmt.Sprintf("Slices are in states: %d ACTIVE", tc.replicas),
						}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
					}, utils.LongTimeout, utils.Timeout).Should(gomega.Succeed())
				})

				ginkgo.By("Deleting JobSet", func() {
					utils.ExpectObjectToBeDeleted(ctx, k8sClient, jobSet, true)
				})

				for i := int32(0); i < tc.replicas; i++ {
					ginkgo.By(fmt.Sprintf("Checking that Slice %d is deleted", i), func() {
						utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlices[i], false)
					})
				}

				ginkgo.By("Checking that Workload is deleted", func() {
					utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdWorkload, false)
				})
			},
				ginkgo.Entry("TPU topology 4x4x4 split across 2 replicas", testCase{
					tpuTopology:   "4x4x4",
					tpuRequests:   "4",
					parallelism:   16,
					replicas:      2,
					wantSliceSize: 16,
					wantDomains: []tas.TopologyDomainAssignment{
						{
							Values: []string{"kind-worker"},
							Count:  16,
						},
						{
							Values: []string{"kind-worker2"},
							Count:  16,
						},
					},
					wantPartitionIDs: [][]string{{"sb2"}, {"sb3"}},
				}),
				ginkgo.Entry("TPU topology 4x4x4 split across 3 replicas", testCase{
					tpuTopology:   "4x4x4",
					tpuRequests:   "4",
					parallelism:   16,
					replicas:      3,
					wantSliceSize: 16,
					wantDomains: []tas.TopologyDomainAssignment{
						{
							Values: []string{"kind-worker2"},
							Count:  16,
						},
						{
							Values: []string{"kind-worker3"},
							Count:  16,
						},
						{
							Values: []string{"kind-worker4"},
							Count:  16,
						},
					},
					wantPartitionIDs: [][]string{{"sb2"}, {"sb3"}, {"sb4"}},
				}),
			)
		})

		ginkgo.It("should delete the Workload finalizer after all Pods have gracefully terminated", func() {
			jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
				Queue(lq.Name).
				ReplicatedJobs(
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj1",
						Image:       utils.E2eTestAgnHostImage,
						Args:        utils.BehaviorWaitForDeletion,
						Replicas:    1,
						Parallelism: 16,
						Completions: 16,
						PodAnnotations: map[string]string{
							core.TPUSliceTopologyAnnotation: "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
						},
						TerminationGracePeriodSeconds: 60,
						LifecyclePreStopSleepSeconds:  60,
					},
				).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj()

			ginkgo.By("Creating a JobSet", func() {
				utils.MustCreate(ctx, k8sClient, jobSet)
			})

			createdWorkload := &kueue.Workload{}
			wlKey := types.NamespacedName{
				Name:      jobsetcontroller.GetWorkloadNameForJobSet(jobSet.Name, jobSet.UID),
				Namespace: ns.Name,
			}

			ginkgo.By("Waiting for Admission of the Workload", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			createdSlice := &slice.Slice{}
			sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1", 0)

			ginkgo.By("Checking that Slice is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding Ready condition", func() {
				utils.SetSliceReady(ctx, k8sClient, sliceKey, "4x4x4")
			})

			ginkgo.By("Checking that the Workload is admitted", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeTrue())
				}, utils.LongTimeout, utils.Timeout).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that all pods are running", func() {
				pods := &corev1.PodList{}
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.List(ctx, pods, client.InNamespace(ns.Name))).To(gomega.Succeed())
					g.Expect(pods.Items).Should(gomega.HaveLen(16))
					for _, pod := range pods.Items {
						g.Expect(pod.Status.Phase).To(gomega.Equal(corev1.PodRunning))
						g.Expect(pod.Spec.NodeSelector).To(gomega.HaveKeyWithValue(core.TPUTopologyAnnotation, "4x4x4"))
					}
				}, util.LongTimeout, util.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Deactivating the Workload", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					createdWorkload.Spec.Active = ptr.To(false)
					g.Expect(k8sClient.Update(ctx, createdWorkload)).Should(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that Slice is still exists and waiting for Pods termination", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
				}, utils.ConsistentDuration, utils.ShortInterval).Should(gomega.Succeed())
			})

			ginkgo.By("Deleting the Pods", func() {
				utils.DeleteAllPodsInNamespace(ctx, k8sClient, ns)
			})

			ginkgo.By("Checking that the Slice is deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice, false)
			})
		})

		ginkgo.It("should recover after Slice creation failed", func() {
			jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
				Queue(lq.Name).
				ReplicatedJobs(
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj1",
						Image:       utils.E2eTestAgnHostImage,
						Args:        utils.BehaviorWaitForDeletion,
						Replicas:    1,
						Parallelism: 16,
						Completions: 16,
						PodAnnotations: map[string]string{
							core.TPUSliceTopologyAnnotation: "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
						},
					},
				).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj()

			ginkgo.By("Creating a JobSet", func() {
				utils.MustCreate(ctx, k8sClient, jobSet)
			})

			createdWorkload := &kueue.Workload{}
			wlKey := types.NamespacedName{
				Name:      jobsetcontroller.GetWorkloadNameForJobSet(jobSet.Name, jobSet.UID),
				Namespace: ns.Name,
			}

			ginkgo.By("Waiting for Admission of the Workload", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			createdSlice := &slice.Slice{}
			sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1", 0)
			var oldCube string

			var oldSliceUID types.UID
			var oldDomains []tas.TopologyDomainAssignment
			ginkgo.By("Verifying initial TopologyAssignment", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
					g.Expect(createdWorkload.Status.Admission.PodSetAssignments).Should(gomega.HaveLen(1))
					assignment := createdWorkload.Status.Admission.PodSetAssignments[0].TopologyAssignment
					g.Expect(assignment).ShouldNot(gomega.BeNil())
					oldDomains = tas.InternalFrom(assignment).Domains
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that Slice is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					g.Expect(createdSlice.Spec.PartitionIds).To(gomega.HaveLen(1))
					oldCube = createdSlice.Spec.PartitionIds[0]
					oldSliceUID = createdSlice.GetUID()
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Admission Check state is pending", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStatePending,
						Message: `Slices are in states: 1 CREATED`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By(fmt.Sprintf("Setting the old cube %s to unhealthy", oldCube), func() {
				var nodeName string
				gomega.Eventually(func(g gomega.Gomega) {
					nodes := &corev1.NodeList{}
					g.Expect(k8sClient.List(ctx, nodes)).To(gomega.Succeed())
					for _, node := range nodes.Items {
						if node.Labels[core.TPUSubBlockLabel] == oldCube {
							nodeName = node.Name
							break
						}
					}
					g.Expect(nodeName).NotTo(gomega.BeEmpty())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())

				gomega.Eventually(func(g gomega.Gomega) {
					node := &corev1.Node{}
					g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: nodeName}, node)).To(gomega.Succeed())
					node.Labels[core.TPUSliceHealthNodeSelectorKey] = "UNHEALTHY"
					g.Expect(k8sClient.Update(ctx, node)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())

				ginkgo.DeferCleanup(func(name string) {
					gomega.Eventually(func(g gomega.Gomega) {
						node := &corev1.Node{}
						g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: name}, node)).To(gomega.Succeed())
						node.Labels[core.TPUSliceHealthNodeSelectorKey] = core.TPUSliceHealthNodeSelectorHealthy
						g.Expect(k8sClient.Update(ctx, node)).To(gomega.Succeed())
					}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
				}, nodeName)
			})

			ginkgo.By("Setting Slice state to error", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
						Type:    slice.SliceStateConditionType,
						Status:  metav1.ConditionFalse,
						Reason:  string(core.SliceCreationFailed),
						Message: "Slice creation failed",
					})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Verifying new TopologyAssignment", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
					g.Expect(createdWorkload.Status.Admission.PodSetAssignments).Should(gomega.HaveLen(1))
					newAssignment := createdWorkload.Status.Admission.PodSetAssignments[0].TopologyAssignment
					g.Expect(newAssignment).ShouldNot(gomega.BeNil())
					newDomains := tas.InternalFrom(newAssignment).Domains
					g.Expect(newDomains).ShouldNot(gomega.BeComparableTo(oldDomains))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that a new Slice is created without the unhealthy cube", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					g.Expect(createdSlice.GetUID()).ShouldNot(gomega.Equal(oldSliceUID))
					g.Expect(createdSlice.Spec.PartitionIds).ShouldNot(gomega.ContainElement(oldCube))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Admission Check state is pending", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStatePending,
						Message: `Slices are in states: 1 CREATED`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates", "RetryCount", "RequeueAfterSeconds")))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding ready condition to the new Slice", func() {
				utils.SetSliceReady(ctx, k8sClient, sliceKey, "4x4x4")
			})

			ginkgo.By("Checking that the Admission Check state is ready", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStateReady,
						Message: `Slices are in states: 1 ACTIVE`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates", "RetryCount", "RequeueAfterSeconds")))
					g.Expect(createdWorkload.Status.SchedulingStats.Evictions).Should(gomega.HaveLen(1))
				}, utils.LongTimeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Deleting JobSet", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, jobSet, true)
			})

			ginkgo.By("Checking that Slice is deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice, false)
			})

			ginkgo.By("Checking that Workload is deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdWorkload, false)
			})
		})

		ginkgo.It("should recover after a ready Slice changes to error state", func() {
			jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
				Queue(lq.Name).
				ReplicatedJobs(
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj1",
						Image:       utils.E2eTestAgnHostImage,
						Args:        utils.BehaviorWaitForDeletion,
						Replicas:    1,
						Parallelism: 16,
						Completions: 16,
						PodAnnotations: map[string]string{
							core.TPUSliceTopologyAnnotation: "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
						},
					},
				).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj()

			ginkgo.By("Creating a JobSet", func() {
				utils.MustCreate(ctx, k8sClient, jobSet)
			})

			createdWorkload := &kueue.Workload{}
			wlKey := types.NamespacedName{
				Name:      jobsetcontroller.GetWorkloadNameForJobSet(jobSet.Name, jobSet.UID),
				Namespace: ns.Name,
			}

			ginkgo.By("Waiting for admission of the Workload", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			createdSlice := &slice.Slice{}
			sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1", 0)
			var oldSliceUID types.UID
			var oldPartitionID string
			ginkgo.By("Checking that Slice is created and making it ready", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					oldSliceUID = createdSlice.GetUID()
					meta.SetStatusCondition(
						&createdSlice.Status.Conditions,
						metav1.Condition{
							Type:   slice.SliceStateConditionType,
							Status: metav1.ConditionTrue,
							Reason: string(core.MMIGHealthStatusActive)})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the admission check state is ready", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStateReady,
						Message: `Slices are in states: 1 ACTIVE`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Marking nodes as unhealthy", func() {
				gomega.Expect(createdSlice.Spec.PartitionIds).NotTo(gomega.BeEmpty())
				oldPartitionID = createdSlice.Spec.PartitionIds[0]
				nodes := &corev1.NodeList{}
				gomega.Expect(k8sClient.List(ctx, nodes, client.MatchingLabels{core.TPUSubBlockLabel: oldPartitionID})).To(gomega.Succeed())
				for _, node := range nodes.Items {
					gomega.Eventually(func(g gomega.Gomega) {
						n := &corev1.Node{}
						g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(&node), n)).To(gomega.Succeed())
						n.Labels[core.TPUSliceHealthNodeSelectorKey] = "UNHEALTHY"
						g.Expect(k8sClient.Update(ctx, n)).To(gomega.Succeed())
					}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
				}

				ginkgo.DeferCleanup(func() {
					nodes := &corev1.NodeList{}
					gomega.Expect(k8sClient.List(ctx, nodes, client.MatchingLabels{core.TPUSubBlockLabel: oldPartitionID})).To(gomega.Succeed())
					for _, node := range nodes.Items {
						gomega.Eventually(func(g gomega.Gomega) {
							n := &corev1.Node{}
							g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(&node), n)).To(gomega.Succeed())
							n.Labels[core.TPUSliceHealthNodeSelectorKey] = core.TPUSliceHealthNodeSelectorHealthy
							g.Expect(k8sClient.Update(ctx, n)).To(gomega.Succeed())
						}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
					}
				})
			})

			ginkgo.By("Changing Slice condition to error", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice.Status.Conditions,
						metav1.Condition{
							Type:    slice.SliceStateConditionType,
							Status:  metav1.ConditionFalse,
							Reason:  string(core.MMIGHealthStatusFailed),
							Message: "Slice has an error"})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Admission Check state is reset to pending", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStatePending,
						Message: `Slices are in states: 1 CREATED`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates", "RetryCount", "RequeueAfterSeconds")))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that a new Slice is created using a different partition ID", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					g.Expect(createdSlice.GetUID()).ShouldNot(gomega.Equal(oldSliceUID))
					g.Expect(createdSlice.Spec.PartitionIds).ShouldNot(gomega.ContainElement(oldPartitionID))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding ready condition to the new Slice", func() {
				utils.SetSliceReady(ctx, k8sClient, sliceKey, "4x4x4")
			})

			ginkgo.By("Checking that the Workload is admitted and the Admission Check state is ready", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStateReady,
						Message: `Slices are in states: 1 ACTIVE`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates", "RetryCount", "RequeueAfterSeconds")))
					g.Expect(createdWorkload.Status.SchedulingStats).ShouldNot(gomega.BeNil())
					g.Expect(createdWorkload.Status.SchedulingStats.Evictions).Should(gomega.HaveLen(1))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})
			ginkgo.By("Checking that all pods are running with topology node selector", func() {
				pods := &corev1.PodList{}
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.List(ctx, pods, client.InNamespace(ns.Name))).To(gomega.Succeed())
					g.Expect(pods.Items).Should(gomega.HaveLen(int(16)))
					for _, pod := range pods.Items {
						g.Expect(pod.Status.Phase).To(gomega.Equal(corev1.PodRunning))
						g.Expect(pod.Spec.NodeSelector).To(gomega.HaveKeyWithValue(core.TPUTopologyAnnotation, "4x4x4"))
					}
				}, utils.LongTimeout, utils.Interval).Should(gomega.Succeed())
			})
		})

		ginkgo.It("should recover after Slice is stale during initialization", func() {
			jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
				Queue(lq.Name).
				ReplicatedJobs(
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj1",
						Image:       utils.E2eTestAgnHostImage,
						Args:        utils.BehaviorWaitForDeletion,
						Replicas:    1,
						Parallelism: 16,
						Completions: 16,
						PodAnnotations: map[string]string{
							core.TPUSliceTopologyAnnotation: "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
						},
					},
				).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj()

			ginkgo.By("Creating a JobSet", func() {
				utils.MustCreate(ctx, k8sClient, jobSet)
			})

			createdWorkload := &kueue.Workload{}
			wlKey := types.NamespacedName{
				Name:      jobsetcontroller.GetWorkloadNameForJobSet(jobSet.Name, jobSet.UID),
				Namespace: ns.Name,
			}

			ginkgo.By("Waiting for Admission of the Workload", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			createdSlice := &slice.Slice{}
			sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1", 0)

			var oldSliceUID types.UID
			ginkgo.By("Checking that Slice is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					oldSliceUID = createdSlice.GetUID()
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Setting Slice state to forming", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
						Type:               slice.SliceStateConditionType,
						Status:             metav1.ConditionFalse,
						Reason:             string(core.MMIGHealthStatusActivating),
						LastTransitionTime: metav1.NewTime(time.Now().Add(-3 * time.Minute)),
						Message:            "Slice is stale",
					})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that a new Slice is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					g.Expect(createdSlice.GetUID()).ShouldNot(gomega.Equal(oldSliceUID))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding ready condition to the new Slice", func() {
				utils.SetSliceReady(ctx, k8sClient, sliceKey, "4x4x4")
			})

			ginkgo.By("Checking that the Admission Check state is ready", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStateReady,
						Message: `Slices are in states: 1 ACTIVE`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates", "RetryCount")))
				}, utils.LongTimeout, utils.Interval).Should(gomega.Succeed())
			})
		})
		ginkgo.It("should create multiple Slices", func() {
			jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
				Queue(lq.Name).
				ReplicatedJobs(
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj1",
						Image:       utils.E2eTestAgnHostImage,
						Args:        utils.BehaviorWaitForDeletion,
						Replicas:    1,
						Parallelism: 16,
						Completions: 16,
						PodAnnotations: map[string]string{
							core.TPUSliceTopologyAnnotation: "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
						},
					},
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj2",
						Image:       utils.E2eTestAgnHostImage,
						Args:        utils.BehaviorWaitForDeletion,
						Replicas:    1,
						Parallelism: 16,
						Completions: 16,
						PodAnnotations: map[string]string{
							core.TPUSliceTopologyAnnotation: "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
						},
					},
				).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				RequestAndLimit("rj2", core.TPUResourceName, "4").
				Obj()

			ginkgo.By("Creating a JobSet", func() {
				utils.MustCreate(ctx, k8sClient, jobSet)
			})

			createdJobSet := &jobset.JobSet{}

			ginkgo.By("Checking that the JobSet is created with annotations", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(jobSet), createdJobSet)).To(gomega.Succeed())
					for _, replicatedJob := range createdJobSet.Spec.ReplicatedJobs {
						annotations := replicatedJob.Template.Spec.Template.Annotations
						g.Expect(annotations["kueue.x-k8s.io/podset-required-topology"]).
							Should(gomega.Equal("cloud.google.com/gce-topology-block"))
						g.Expect(annotations["kueue.x-k8s.io/podset-slice-required-topology"]).
							Should(gomega.Equal(core.TPUSubBlockLabel))
						g.Expect(annotations["kueue.x-k8s.io/podset-slice-size"]).
							Should(gomega.Equal(strconv.Itoa(16)))
					}
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			createdWorkload := &kueue.Workload{}
			wlKey := types.NamespacedName{
				Name:      jobsetcontroller.GetWorkloadNameForJobSet(jobSet.Name, jobSet.UID),
				Namespace: ns.Name,
			}

			ginkgo.By("Validating the Workload", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).To(gomega.Succeed())
					g.Expect(createdWorkload.Spec.PodSets).To(gomega.HaveLen(2))
					g.Expect(createdWorkload.Spec.PodSets[0].TopologyRequest).To(gomega.BeComparableTo(&kueue.PodSetTopologyRequest{
						Required:                    ptr.To("cloud.google.com/gce-topology-block"),
						PodSetSliceRequiredTopology: ptr.To(core.TPUSubBlockLabel),
						SubGroupCount:               ptr.To[int32](1),
						PodSetSliceSize:             ptr.To[int32](16),
					}, ignorePodSetTopologyRequestFields))
					g.Expect(createdWorkload.Spec.PodSets[1].TopologyRequest).To(gomega.BeComparableTo(&kueue.PodSetTopologyRequest{
						Required:                    ptr.To("cloud.google.com/gce-topology-block"),
						PodSetSliceRequiredTopology: ptr.To(core.TPUSubBlockLabel),
						SubGroupCount:               ptr.To[int32](1),
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
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments).Should(gomega.HaveLen(2))

				assignment1 := tas.InternalFrom(createdWorkload.Status.Admission.PodSetAssignments[0].TopologyAssignment)
				gomega.Expect(assignment1.Levels).Should(gomega.Equal([]string{"kubernetes.io/hostname"}))
				gomega.Expect(assignment1.Domains).Should(gomega.BeComparableTo([]tas.TopologyDomainAssignment{{
					Values: []string{"kind-worker"},
					Count:  16,
				}}))

				assignment2 := tas.InternalFrom(createdWorkload.Status.Admission.PodSetAssignments[1].TopologyAssignment)
				gomega.Expect(assignment2.Levels).Should(gomega.Equal([]string{"kubernetes.io/hostname"}))
				gomega.Expect(assignment2.Domains).Should(gomega.BeComparableTo([]tas.TopologyDomainAssignment{{
					Values: []string{"kind-worker2"},
					Count:  16,
				}}))
			})

			createdSlice1 := &slice.Slice{}
			sliceKey1 := core.SliceKeyFromWorkload(createdWorkload, "rj1", 0)

			ginkgo.By("Checking that Slice 1 is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey1, createdSlice1)).To(gomega.Succeed())
					g.Expect(createdSlice1.Spec.PartitionIds).To(gomega.HaveLen(1))
					g.Expect(createdSlice1.Spec.PartitionIds).To(gomega.BeComparableTo([]string{"sb1"}))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			createdSlice2 := &slice.Slice{}
			sliceKey2 := core.SliceKeyFromWorkload(createdWorkload, "rj2", 0)

			ginkgo.By("Checking that Slice 2 is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey2, createdSlice2)).To(gomega.Succeed())
					g.Expect(createdSlice2.Spec.PartitionIds).To(gomega.HaveLen(1))
					g.Expect(createdSlice2.Spec.PartitionIds).To(gomega.BeComparableTo([]string{"sb2"}))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Workload waiting for admission", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeFalse())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStatePending,
						Message: `Slices are in states: 2 CREATED`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding Forming condition for Slice 1", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey1, createdSlice1)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice1.Status.Conditions, metav1.Condition{
						Type:    slice.SliceStateConditionType,
						Status:  metav1.ConditionFalse,
						Reason:  string(core.MMIGHealthStatusActivating),
						Message: "Test",
					})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice1)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Workload still waiting for admission", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeFalse())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStatePending,
						Message: `Slices are in states: 1 CREATED, 1 ACTIVATING`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
				}, utils.LongTimeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding Activating condition for Slice 2", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey2, createdSlice2)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice2.Status.Conditions, metav1.Condition{
						Type:    slice.SliceStateConditionType,
						Status:  metav1.ConditionFalse,
						Reason:  string(core.MMIGHealthStatusActivating),
						Message: "Test",
					})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice2)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Workload still waiting for admission", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeFalse())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStatePending,
						Message: `Slices are in states: 2 ACTIVATING`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
				}, utils.LongTimeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding Active condition for Slice 1", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey1, createdSlice1)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice1.Status.Conditions, metav1.Condition{
						Type:    slice.SliceStateConditionType,
						Status:  metav1.ConditionTrue,
						Reason:  string(core.MMIGHealthStatusActive),
						Message: "Test",
					})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice1)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Workload still waiting for admission", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeFalse())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStatePending,
						Message: `Slices are in states: 1 ACTIVATING, 1 ACTIVE`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
				}, utils.LongTimeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding Active condition for Slice 2", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey2, createdSlice2)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice2.Status.Conditions, metav1.Condition{
						Type:    slice.SliceStateConditionType,
						Status:  metav1.ConditionTrue,
						Reason:  string(core.MMIGHealthStatusActive),
						Message: "Test",
					})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice2)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Workload is admitted and admission check status is ready", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeTrue())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStateReady,
						Message: `Slices are in states: 2 ACTIVE`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
				}, utils.LongTimeout, utils.Timeout).Should(gomega.Succeed())
			})

			ginkgo.By("Deleting JobSet", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, jobSet, true)
			})

			ginkgo.By("Checking that Slices are deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice1, false)
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice2, false)
			})

			ginkgo.By("Checking that Workload is deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdWorkload, false)
			})
		})

		ginkgo.It("should evict Workload if Slice is deleted manually while Workload is running", func() {
			jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
				Queue(lq.Name).
				ReplicatedJobs(
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj1",
						Image:       utils.E2eTestAgnHostImage,
						Args:        utils.BehaviorWaitForDeletion,
						Replicas:    1,
						Parallelism: 16,
						Completions: 16,
						PodAnnotations: map[string]string{
							core.TPUSliceTopologyAnnotation: "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
						},
					},
				).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj()

			ginkgo.By("Creating a JobSet", func() {
				utils.MustCreate(ctx, k8sClient, jobSet)
			})

			createdWorkload := &kueue.Workload{}
			wlKey := types.NamespacedName{
				Name:      jobsetcontroller.GetWorkloadNameForJobSet(jobSet.Name, jobSet.UID),
				Namespace: ns.Name,
			}

			ginkgo.By("Waiting for Admission of the Workload", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			createdSlice := &slice.Slice{}
			sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1", 0)
			var oldSliceUID types.UID

			ginkgo.By("Checking that Slice is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					oldSliceUID = createdSlice.GetUID()
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding Ready condition", func() {
				utils.SetSliceReady(ctx, k8sClient, sliceKey, "4x4x4")
			})

			ginkgo.By("Checking that the Workload is admitted", func() {
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

			ginkgo.By("Deleting the Slice", func() {
				gomega.Expect(k8sClient.Delete(ctx, createdSlice)).To(gomega.Succeed())
			})

			ginkgo.By("Checking that the Workload has been evicted", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.SchedulingStats).ShouldNot(gomega.BeNil())
					g.Expect(createdWorkload.Status.SchedulingStats.Evictions).Should(gomega.HaveLen(1))
				}, utils.LongTimeout, utils.Timeout).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that a new Slice is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					g.Expect(createdSlice.GetUID()).ShouldNot(gomega.Equal(oldSliceUID))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Admission Check state is pending", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStatePending,
						Message: `Slices are in states: 1 CREATED`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates", "RetryCount", "RequeueAfterSeconds")))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding Ready condition to the new Slice", func() {
				utils.SetSliceReady(ctx, k8sClient, sliceKey, "4x4x4")
			})

			ginkgo.By("Checking that the Workload is admitted again", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeTrue())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStateReady,
						Message: `Slices are in states: 1 ACTIVE`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates", "RetryCount", "RequeueAfterSeconds")))
				}, utils.LongTimeout, utils.Timeout).Should(gomega.Succeed())
			})

			ginkgo.By("Deleting JobSet", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, jobSet, true)
			})

			ginkgo.By("Checking that Slice is deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice, false)
			})

			ginkgo.By("Checking that Workload is deleted", func() {
				utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdWorkload, false)
			})
		})
	})
})
