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
	kueuealpha "sigs.k8s.io/kueue/apis/kueue/v1alpha1"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	jobsetcontroller "sigs.k8s.io/kueue/pkg/controller/jobs/jobset"
	"sigs.k8s.io/kueue/pkg/workload"
	"sigs.k8s.io/kueue/test/util"

	slice "tpu-slice-controller/api/v1alpha1"
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
			Levels("cloud.google.com/gce-topology-block", "cloud.google.com/gke-tpu-slice-4x4x4-id", "kubernetes.io/hostname").
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
			replicas         int32
			wantSliceSize    int32
			tpuRequests      string
			unhealthyNodes   []string
			wantDomains      []kueue.TopologyDomainAssignment
			wantPartitionIds []string
		}
		ginkgo.DescribeTable("it should create Slice based on created Workload with",
			func(tc testCase) {
				for _, unhealthyNode := range tc.unhealthyNodes {
					node := &corev1.Node{}
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: unhealthyNode}, node)).To(gomega.Succeed())
						delete(node.Labels, "cloud.google.com/gke-tpu-slice-4x4x4-health")
						g.Expect(k8sClient.Update(ctx, node)).To(gomega.Succeed())
					}, util.Timeout, util.Interval).Should(gomega.Succeed())
				}
				// Revert changes after test
				ginkgo.DeferCleanup(func() {
					for _, unhealthyNode := range tc.unhealthyNodes {
						node := &corev1.Node{}
						gomega.Eventually(func(g gomega.Gomega) {
							g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: unhealthyNode}, node)).To(gomega.Succeed())
							node.Labels["cloud.google.com/gke-tpu-slice-4x4x4-health"] = "true"
							g.Expect(k8sClient.Update(ctx, node)).To(gomega.Succeed())
						}, util.Timeout, util.Interval).Should(gomega.Succeed())
					}
				})

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
								"cloud.google.com/gke-tpu-topology": tc.tpuTopology,
							},
							NodeSelector: map[string]string{
								"cloud.google.com/gke-tpu-accelerator": "tpu-v7x",
							},
						},
					).
					RequestAndLimit("rj1", extraResource, tc.tpuRequests).
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
								Should(gomega.Equal("cloud.google.com/gke-tpu-slice-4x4x4-id"))
							g.Expect(annotations["kueue.x-k8s.io/podset-slice-size"]).
								Should(gomega.Equal(fmt.Sprint(tc.wantSliceSize)))

							// node health
							g.Expect(replicatedJob.Template.Spec.Template.Spec.NodeSelector["cloud.google.com/gke-tpu-slice-4x4x4-health"]).Should(gomega.Equal("true"))
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
							PodSetSliceRequiredTopology: ptr.To("cloud.google.com/gke-tpu-slice-4x4x4-id"),
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
					gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments[0].TopologyAssignment).Should(gomega.BeComparableTo(
						&kueue.TopologyAssignment{
							Levels:  []string{"kubernetes.io/hostname"},
							Domains: tc.wantDomains,
						},
					))
				})

				createdSlice := &slice.Slice{}
				sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1")

				ginkgo.By("Checking that Slice is created", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
						g.Expect(createdSlice.Spec.PartitionIds).To(gomega.HaveLen(len(tc.wantPartitionIds)))
						g.Expect(createdSlice.Spec.PartitionIds).To(gomega.BeComparableTo(tc.wantPartitionIds))
						g.Expect(createdSlice.Spec.Topology).To(gomega.Equal(tc.tpuTopology))
						g.Expect(createdSlice.Spec.Type).To(gomega.Equal(slice.Type("tpu-v7x")))
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
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
						meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
							Type:    slice.SliceStateConditionType,
							Status:  metav1.ConditionTrue,
							Reason:  string(core.MMIGHealthStatusActive),
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
							Message: `Slices are in states: 1 ACTIVE`,
						}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
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
			},
			ginkgo.Entry("TPU topology 4x4x4, TPU topology 4 and parallelism 16", testCase{
				tpuTopology:   "4x4x4",
				tpuRequests:   "4",
				parallelism:   16,
				replicas:      1,
				wantSliceSize: 16,
				wantDomains: []kueue.TopologyDomainAssignment{{
					Values: []string{"kind-worker"},
					Count:  16,
				}},
				wantPartitionIds: []string{"sb1"},
			}),
			ginkgo.Entry("TPU topology 4x4x4, TPU topology 4 and parallelism 16 (missed kind-worker node)", testCase{
				tpuTopology:    "4x4x4",
				tpuRequests:    "4",
				parallelism:    16,
				replicas:       1,
				unhealthyNodes: []string{"kind-worker"},
				wantSliceSize:  16,
				wantDomains: []kueue.TopologyDomainAssignment{{
					Values: []string{"kind-worker2"},
					Count:  16,
				}},
				wantPartitionIds: []string{"sb2"},
			}),
			ginkgo.Entry("TPU topology, TPU topology 1 4x4x4 and parallelism 16", testCase{
				tpuTopology:   "4x4x4",
				tpuRequests:   "1",
				parallelism:   64,
				replicas:      1,
				wantSliceSize: 64,
				wantDomains: []kueue.TopologyDomainAssignment{{
					Values: []string{"kind-worker"},
					Count:  64,
				}},
				wantPartitionIds: []string{"sb1"},
			}),
			ginkgo.Entry("TPU topology 4x4x12 and parallelism 48", testCase{
				tpuTopology:   "4x4x12",
				tpuRequests:   "4",
				parallelism:   48,
				replicas:      1,
				wantSliceSize: 16,
				wantDomains: []kueue.TopologyDomainAssignment{
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
				wantPartitionIds: []string{"sb2", "sb3", "sb4"},
			}),
			ginkgo.Entry("TPU topology 4x4x12 and parallelism 96", testCase{
				tpuTopology:   "4x4x12",
				tpuRequests:   "2",
				parallelism:   96,
				replicas:      1,
				wantSliceSize: 32,
				wantDomains: []kueue.TopologyDomainAssignment{
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
				wantPartitionIds: []string{"sb2", "sb3", "sb4"},
			}),
			ginkgo.Entry("TPU topology 4x4x8 and parallelism 128", testCase{
				tpuTopology:   "4x4x8",
				tpuRequests:   "1",
				parallelism:   128,
				replicas:      1,
				wantSliceSize: 64,
				wantDomains: []kueue.TopologyDomainAssignment{
					{
						Values: []string{"kind-worker2"},
						Count:  64,
					},
					{
						Values: []string{"kind-worker3"},
						Count:  64,
					},
				},
				wantPartitionIds: []string{"sb2", "sb3"},
			}),
			ginkgo.Entry("TPU topology 4x4x4 split across 2 replicas", testCase{
				tpuTopology:   "4x4x4",
				tpuRequests:   "4",
				parallelism:   8,
				replicas:      2,
				wantSliceSize: 16,
				wantDomains: []kueue.TopologyDomainAssignment{
					{
						Values: []string{"kind-worker"},
						Count:  16,
					},
				},
				wantPartitionIds: []string{"sb1"},
			}),
			ginkgo.Entry("TPU topology 4x4x12 split across 3 replicas", testCase{
				tpuTopology:   "4x4x12",
				tpuRequests:   "4",
				parallelism:   16,
				replicas:      3,
				wantSliceSize: 16,
				wantDomains: []kueue.TopologyDomainAssignment{
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
				wantPartitionIds: []string{"sb2", "sb3", "sb4"},
			}),
		)

		ginkgo.It("should delete the Workload finalizer after all Pods have gracefully terminated", func() {
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
							"cloud.google.com/gke-tpu-topology": "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": "tpu-v7x",
						},
						TerminationGracePeriodSeconds: 60,
						LifecyclePreStopSleepSeconds:  60,
					},
				).
				RequestAndLimit("rj1", extraResource, "1").
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
			sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1")

			ginkgo.By("Checking that Slice is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding Ready condition", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
						Type:    slice.SliceStateConditionType,
						Status:  metav1.ConditionTrue,
						Reason:  string(core.MMIGHealthStatusActive),
						Message: "Test",
					})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
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
					g.Expect(pods.Items).Should(gomega.HaveLen(1))
					for _, pod := range pods.Items {
						g.Expect(pod.Status.Phase).To(gomega.Equal(corev1.PodRunning))
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

		ginkgo.It("should recover after Slice is in error state", func() {
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
							"cloud.google.com/gke-tpu-topology": "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": "tpu-v7x",
						},
					},
				).
				RequestAndLimit("rj1", extraResource, "1").
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
			sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1")

			var oldSliceUID types.UID
			ginkgo.By("Checking that Slice is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
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

			ginkgo.By("Setting Slice state to error", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
						Type:    slice.SliceStateConditionType,
						Status:  metav1.ConditionFalse,
						Reason:  string(core.MMIGHealthStatusFailed),
						Message: "Slice has an error",
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

			ginkgo.By("Adding ready condition to the new Slice", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
						Type:    slice.SliceStateConditionType,
						Status:  metav1.ConditionTrue,
						Reason:  string(core.MMIGHealthStatusActive),
						Message: "Slice is ready",
					})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Admission Check state is ready", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStateReady,
						Message: `Slices are in states: 1 ACTIVE`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
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
						Parallelism: 1,
						Completions: 1,
						PodAnnotations: map[string]string{
							"cloud.google.com/gke-tpu-topology": "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": "tpu-v7x",
						},
					},
				).
				RequestAndLimit("rj1", extraResource, "1").
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
			sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1")
			var oldSliceUID types.UID
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
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that a new Slice is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					g.Expect(createdSlice.GetUID()).ShouldNot(gomega.Equal(oldSliceUID))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Adding ready condition to the new Slice", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
						Type:    slice.SliceStateConditionType,
						Status:  metav1.ConditionTrue,
						Reason:  string(core.MMIGHealthStatusActive),
						Message: "Slice is ready",
					})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Workload is admitted and the Admission Check state is ready", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStateReady,
						Message: `Slices are in states: 1 ACTIVE`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
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
						Parallelism: 1,
						Completions: 1,
						PodAnnotations: map[string]string{
							"cloud.google.com/gke-tpu-topology": "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": "tpu-v7x",
						},
					},
				).
				RequestAndLimit("rj1", extraResource, "1").
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
			sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1")

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
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
					meta.SetStatusCondition(&createdSlice.Status.Conditions, metav1.Condition{
						Type:    slice.SliceStateConditionType,
						Status:  metav1.ConditionTrue,
						Reason:  string(core.MMIGHealthStatusActive),
						Message: "Slice is ready",
					})
					g.Expect(k8sClient.Status().Update(ctx, createdSlice)).To(gomega.Succeed())
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			ginkgo.By("Checking that the Admission Check state is ready", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(createdWorkload.Status.AdmissionChecks).Should(gomega.BeComparableTo([]kueue.AdmissionCheckState{{
						Name:    kueue.AdmissionCheckReference(ac.Name),
						State:   kueue.CheckStateReady,
						Message: `Slices are in states: 1 ACTIVE`,
					}}, cmpopts.IgnoreFields(kueue.AdmissionCheckState{}, "LastTransitionTime", "PodSetUpdates")))
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
							"cloud.google.com/gke-tpu-topology": "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": "tpu-v7x",
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
							"cloud.google.com/gke-tpu-topology": "4x4x4",
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": "tpu-v7x",
						},
					},
				).
				RequestAndLimit("rj1", extraResource, "4").
				RequestAndLimit("rj2", extraResource, "4").
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
							Should(gomega.Equal("cloud.google.com/gke-tpu-slice-4x4x4-id"))
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
						PodSetSliceRequiredTopology: ptr.To("cloud.google.com/gke-tpu-slice-4x4x4-id"),
						SubGroupCount:               ptr.To[int32](1),
						PodSetSliceSize:             ptr.To[int32](16),
					}, ignorePodSetTopologyRequestFields))
					g.Expect(createdWorkload.Spec.PodSets[1].TopologyRequest).To(gomega.BeComparableTo(&kueue.PodSetTopologyRequest{
						Required:                    ptr.To("cloud.google.com/gce-topology-block"),
						PodSetSliceRequiredTopology: ptr.To("cloud.google.com/gke-tpu-slice-4x4x4-id"),
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
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments[0].TopologyAssignment).Should(gomega.BeComparableTo(
					&kueue.TopologyAssignment{
						Levels: []string{"kubernetes.io/hostname"},
						Domains: []kueue.TopologyDomainAssignment{{
							Values: []string{"kind-worker"},
							Count:  16,
						}},
					},
				))
				gomega.Expect(createdWorkload.Status.Admission.PodSetAssignments[1].TopologyAssignment).Should(gomega.BeComparableTo(
					&kueue.TopologyAssignment{
						Levels: []string{"kubernetes.io/hostname"},
						Domains: []kueue.TopologyDomainAssignment{{
							Values: []string{"kind-worker2"},
							Count:  16,
						}},
					},
				))
			})

			createdSlice1 := &slice.Slice{}
			sliceKey1 := core.SliceKeyFromWorkload(createdWorkload, "rj1")

			ginkgo.By("Checking that Slice 1 is created", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, sliceKey1, createdSlice1)).To(gomega.Succeed())
					g.Expect(createdSlice1.Spec.PartitionIds).To(gomega.HaveLen(1))
					g.Expect(createdSlice1.Spec.PartitionIds).To(gomega.BeComparableTo([]string{"sb1"}))
				}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
			})

			createdSlice2 := &slice.Slice{}
			sliceKey2 := core.SliceKeyFromWorkload(createdWorkload, "rj2")

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
						Type:    string(slice.SliceStateConditionType),
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
	})
})
