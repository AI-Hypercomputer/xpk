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
	kueuealpha "sigs.k8s.io/kueue/apis/kueue/v1alpha1"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	jobsetcontroller "sigs.k8s.io/kueue/pkg/controller/jobs/jobset"
	"sigs.k8s.io/kueue/pkg/workload"

	slice "tpu-slice-controller/api/v1alpha1"
	"tpu-slice-controller/internal/controller"
	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/util/testing"
	testingjobsjobset "tpu-slice-controller/internal/util/testingjobs/jobset"
	"tpu-slice-controller/test/utils"
)

const (
	tpuAccelerator = "tpu-v7x"
)

var (
	ignorePodSetTopologyRequestFields = cmpopts.IgnoreFields(kueue.PodSetTopologyRequest{}, "PodIndexLabel", "SubGroupIndexLabel")
)

var _ = ginkgo.Describe("JobSet", func() {
	var (
		topology *kueuealpha.Topology
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
			Levels(core.TPUBlockLabel, core.TPUSubBlockLabel).
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
			AdmissionChecks(kueue.AdmissionCheckReference(ac.Name)).
			ResourceGroup(*testing.MakeFlavorQuotas(rf.Name).
				Resource(extraResource, "9999").
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
			wantSliceSize    int32
			tpuRequests      string
			wantDomains      []kueue.TopologyDomainAssignment
			wantNodeSelector map[string][]string
		}
		ginkgo.DescribeTable("it should create Slice based on created Workload with",
			func(tc testCase) {
				jobSet := testingjobsjobset.MakeJobSet("jobset", ns.Name).
					Queue(lq.Name).
					ReplicatedJobs(
						testingjobsjobset.ReplicatedJobRequirements{
							Name:        "rj1",
							Image:       utils.E2eTestAgnHostImage,
							Args:        utils.BehaviorWaitForDeletion,
							Replicas:    1,
							Parallelism: tc.parallelism,
							Completions: tc.parallelism,
							PodAnnotations: map[string]string{
								core.TPUTopologyAnnotation: tc.tpuTopology,
							},
							NodeSelector: map[string]string{
								core.TPUAcceleratorLabel: tpuAccelerator,
							},
						},
					).
					RequestAndLimit("rj1", extraResource, tc.tpuRequests).
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
							g.Expect(annotations[kueuealpha.PodSetRequiredTopologyAnnotation]).
								Should(gomega.Equal(core.TPUBlockLabel))
							g.Expect(annotations[kueuealpha.PodSetSliceRequiredTopologyAnnotation]).
								Should(gomega.Equal(core.TPUSubBlockLabel))
							g.Expect(annotations[kueuealpha.PodSetSliceSizeAnnotation]).
								Should(gomega.Equal(fmt.Sprint(tc.wantSliceSize)))
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
							Required:                    ptr.To(core.TPUBlockLabel),
							PodSetSliceRequiredTopology: ptr.To(core.TPUSubBlockLabel),
							SubGroupCount:               ptr.To[int32](1),
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
					gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments[0].TopologyAssignment).Should(gomega.BeComparableTo(
						&kueue.TopologyAssignment{
							Levels:  []string{core.TPUBlockLabel, core.TPUSubBlockLabel},
							Domains: tc.wantDomains,
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
						g.Expect(createdSlice.Spec.NodeSelector).To(gomega.BeComparableTo(tc.wantNodeSelector))
					}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
				})

				ginkgo.By("Checking that the Workload waiting for admission", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
						g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeFalse())
						g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
							Name:    kueue.AdmissionCheckReference(ac.Name),
							State:   kueue.CheckStatePending,
							Message: fmt.Sprintf("The Slice %s/%s has been created", createdSlice.Namespace, createdSlice.Name),
						}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
					}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
				})

				ginkgo.By("Adding Forming condition", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
						meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
							Type:    string(slice.Forming),
							Status:  metav1.ConditionTrue,
							Reason:  "Test",
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
							Message: fmt.Sprintf("The Slice %q is being formed", createdSlice.Name),
						}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
					}, utils.LongTimeout, utils.Interval).Should(gomega.Succeed())
				})

				ginkgo.By("Adding Ready condition", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
						meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
							Type:    string(slice.Forming),
							Status:  metav1.ConditionFalse,
							Reason:  "Test",
							Message: "Test",
						})
						meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
							Type:    string(slice.Ready),
							Status:  metav1.ConditionTrue,
							Reason:  "Test",
							Message: "Test",
						})
						g.Expect(k8sClient.Status().Update(ctx, createdSlice)).To(gomega.Succeed())
					}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
				})

				ginkgo.By("Checking that the Workload is admitted and admission check status is ready", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
						g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeTrue())
						g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
							Name:    kueue.AdmissionCheckReference(ac.Name),
							State:   kueue.CheckStateReady,
							Message: fmt.Sprintf("The Slice %q is fully operational", createdWorkload.Name),
						}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
					}, utils.LongTimeout, utils.Timeout).Should(gomega.Succeed())
				})

				ginkgo.By("Deleting JobSet", func() {
					utils.ExpectObjectToBeDeleted(ctx, k8sClient, jobSet, true)
				})

				ginkgo.By("Checking that Slice is deleted", func() {
					utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice, false)
				})
			},
			ginkgo.Entry("TPU topology 4x4x4 and parallelism 16", testCase{
				tpuTopology:   "4x4x4",
				tpuRequests:   "4",
				parallelism:   16,
				wantSliceSize: 16,
				wantDomains: []kueue.TopologyDomainAssignment{{
					Values: []string{"b1", "sb1"},
					Count:  16,
				}},
				wantNodeSelector: map[string][]string{
					controller.TPUReservationSubblockLabel: {"sb1"},
				},
			}),
			ginkgo.Entry("TPU topology 4x4x4 and parallelism 16", testCase{
				tpuTopology:   "4x4x4",
				tpuRequests:   "1",
				parallelism:   64,
				wantSliceSize: 64,
				wantDomains: []kueue.TopologyDomainAssignment{{
					Values: []string{"b1", "sb1"},
					Count:  64,
				}},
				wantNodeSelector: map[string][]string{
					controller.TPUReservationSubblockLabel: {"sb1"},
				},
			}),
			ginkgo.Entry("TPU topology 4x4x12 and parallelism 48", testCase{
				tpuTopology:   "4x4x12",
				tpuRequests:   "4",
				parallelism:   48,
				wantSliceSize: 16,
				wantDomains: []kueue.TopologyDomainAssignment{
					{
						Values: []string{"b2", "sb2"},
						Count:  16,
					},
					{
						Values: []string{"b2", "sb3"},
						Count:  16,
					},
					{
						Values: []string{"b2", "sb4"},
						Count:  16,
					},
				},
				wantNodeSelector: map[string][]string{
					controller.TPUReservationSubblockLabel: {"sb2", "sb3", "sb4"},
				},
			}),
			ginkgo.Entry("TPU topology 4x4x12 and parallelism 96", testCase{
				tpuTopology:   "4x4x12",
				tpuRequests:   "2",
				parallelism:   96,
				wantSliceSize: 32,
				wantDomains: []kueue.TopologyDomainAssignment{
					{
						Values: []string{"b2", "sb2"},
						Count:  32,
					},
					{
						Values: []string{"b2", "sb3"},
						Count:  32,
					},
					{
						Values: []string{"b2", "sb4"},
						Count:  32,
					},
				},
				wantNodeSelector: map[string][]string{
					controller.TPUReservationSubblockLabel: {"sb2", "sb3", "sb4"},
				},
			}),
			ginkgo.Entry("TPU topology 4x4x8 and parallelism 128", testCase{
				tpuTopology:   "4x4x8",
				tpuRequests:   "1",
				parallelism:   128,
				wantSliceSize: 64,
				wantDomains: []kueue.TopologyDomainAssignment{
					{
						Values: []string{"b2", "sb2"},
						Count:  64,
					},
					{
						Values: []string{"b2", "sb3"},
						Count:  64,
					},
				},
				wantNodeSelector: map[string][]string{
					controller.TPUReservationSubblockLabel: {"sb2", "sb3"},
				},
			}),
		)
	})
})
