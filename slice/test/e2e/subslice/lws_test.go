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

package subslicee2e

import (
	"fmt"

	"github.com/onsi/ginkgo/v2"
	"github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta2"
	"sigs.k8s.io/kueue/pkg/workload"
	leaderworkersetv1 "sigs.k8s.io/lws/api/leaderworkerset/v1"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/controller"
	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/util/testing"
	testingjobslws "tpu-slice-controller/internal/util/testingjobs/leaderworkerset"
	"tpu-slice-controller/test/utils"
)

var _ = ginkgo.Describe("LWS Subslicing", func() {
	var (
		topology *kueue.Topology
		ns       *corev1.Namespace
		rf       *kueue.ResourceFlavor
		ac       *kueue.AdmissionCheck
		cq       *kueue.ClusterQueue
		lq       *kueue.LocalQueue
	)

	ginkgo.BeforeEach(func() {
		ns = testing.MakeNamespaceWithGenerateName("e2e-lws-subslicing-")
		utils.MustCreate(ctx, k8sClient, ns)

		topology = testing.MakeTopology("topology-lws-subslicing").
			Levels("cloud.google.com/gce-topology-block",
				core.TPUSubBlockLabel,
				"cloud.google.com/gke-tpu-partition-2x4x4-id",
				"cloud.google.com/gke-tpu-partition-2x2x4-id",
				"cloud.google.com/gke-tpu-partition-2x2x2-id",
				"cloud.google.com/gke-tpu-partition-2x2x1-id",
				"kubernetes.io/hostname").
			Obj()
		utils.MustCreate(ctx, k8sClient, topology)

		rf = testing.MakeResourceFlavor("rf-lws-subslicing").
			NodeLabel(nodeGroupLabel, nodeGroup).
			TopologyName(topology.Name).
			Obj()
		utils.MustCreate(ctx, k8sClient, rf)

		ac = testing.MakeAdmissionCheck("ac-lws-subslicing").ControllerName(controller.SliceControllerName).Obj()
		utils.MustCreate(ctx, k8sClient, ac)

		cq = testing.MakeClusterQueue("cq-lws-subslicing").
			AdmissionChecks(ac.Name).
			ResourceGroup(*testing.MakeFlavorQuotas(rf.Name).
				Resource(core.TPUResourceName, "9999").
				Obj()).
			Obj()
		utils.MustCreate(ctx, k8sClient, cq)

		lq = testing.MakeLocalQueue("lq-lws-subslicing", ns.Name).ClusterQueue(cq.Name).Obj()
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

	type testCase struct {
		topology        string
		size            int32
		wantPartitionID string
		withLeader      bool
	}

	ginkgo.DescribeTable("should create Slice for", func(tc testCase) {
		name := fmt.Sprintf("lws-%s", tc.topology)
		if tc.withLeader {
			name += "-leader"
		}
		wrapper := testingjobslws.MakeLeaderWorkerSet(name, ns.Name).
			Queue(lq.Name).
			Size(tc.size).
			WorkerImage(utils.E2eTestAgnHostImage).
			WorkerArgs(utils.BehaviorWaitForDeletion...).
			WorkerAnnotation(core.TPUSliceTopologyAnnotation, tc.topology).
			WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
			WorkerRequestAndLimit(core.TPUResourceName, "4")

		if tc.withLeader {
			wrapper = wrapper.
				LeaderAnnotation(core.TPUSliceTopologyAnnotation, tc.topology).
				LeaderNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x))
		}

		lws := wrapper.Obj()
		lws.Spec.StartupPolicy = leaderworkersetv1.LeaderCreatedStartupPolicy
		if tc.withLeader {
			lws.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers = []corev1.Container{{
				Name:  "leader",
				Image: utils.E2eTestAgnHostImage,
				Args:  utils.BehaviorWaitForDeletion,
			}}
		}

		ginkgo.By("Creating a LeaderWorkerSet", func() {
			utils.MustCreate(ctx, k8sClient, lws)
		})

		createdLWS := &leaderworkersetv1.LeaderWorkerSet{}

		ginkgo.By("Checking that the LeaderWorkerSet is created with annotations/selectors", func() {
			gomega.Eventually(func(g gomega.Gomega) {
				g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(lws), createdLWS)).To(gomega.Succeed())

				annotations := createdLWS.Spec.LeaderWorkerTemplate.WorkerTemplate.Annotations
				g.Expect(annotations[kueue.PodSetRequiredTopologyAnnotation]).
					Should(gomega.Equal(fmt.Sprintf("cloud.google.com/gke-tpu-partition-%s-id", tc.topology)))

				templates := []*corev1.PodTemplateSpec{&createdLWS.Spec.LeaderWorkerTemplate.WorkerTemplate}
				if tc.withLeader {
					leaderAnnotations := createdLWS.Spec.LeaderWorkerTemplate.LeaderTemplate.Annotations
					g.Expect(leaderAnnotations["kueue.x-k8s.io/podset-required-topology"]).
						Should(gomega.Equal(fmt.Sprintf("cloud.google.com/gke-tpu-partition-%s-id", tc.topology)))
					templates = append(templates, createdLWS.Spec.LeaderWorkerTemplate.LeaderTemplate)
				}

				for _, template := range templates {
					affinity := template.Spec.Affinity
					g.Expect(affinity).ShouldNot(gomega.BeNil())
					g.Expect(affinity.NodeAffinity).ShouldNot(gomega.BeNil())
					g.Expect(affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution).ShouldNot(gomega.BeNil())
					found := false
					for _, term := range affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms {
						for _, matchExpression := range term.MatchExpressions {
							if matchExpression.Key == fmt.Sprintf("cloud.google.com/gke-tpu-partition-%s-state", tc.topology) {
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
		ginkgo.By("Waiting for Admission of the Workload", func() {
			gomega.Eventually(func(g gomega.Gomega) {
				workloads := &kueue.WorkloadList{}
				g.Expect(k8sClient.List(ctx, workloads, client.InNamespace(ns.Name))).Should(gomega.Succeed())
				g.Expect(workloads.Items).Should(gomega.HaveLen(1))
				*createdWorkload = workloads.Items[0]
				g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
			}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
		})

		ginkgo.By("Checking that the Workload PodSets propagated the topology and accelerator configurations", func() {
			for _, ps := range createdWorkload.Spec.PodSets {
				if ps.Name == "leader" {
					continue
				}
				gomega.Expect(ps.Template.Spec.NodeSelector).To(gomega.HaveKeyWithValue("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)))
			}
		})
		sliceKey := core.SliceKeyFromWorkload(createdWorkload, "main", 0)
		if tc.withLeader {
			sliceKey = core.SliceKeyFromWorkload(createdWorkload, "worker", 0)
		}
		createdSlice := &slice.Slice{}

		ginkgo.By("Checking that SubSlice is created with correct partition id", func() {
			gomega.Eventually(func(g gomega.Gomega) {
				g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
				g.Expect(createdSlice.Spec.PartitionIds).To(gomega.HaveLen(1))
				g.Expect(createdSlice.Spec.PartitionIds[0]).To(gomega.Equal(tc.wantPartitionID))
				g.Expect(createdSlice.Spec.Topology).To(gomega.Equal(tc.topology))
			}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
		})

		ginkgo.By("Adding Ready condition", func() {
			utils.SetSliceReady(ctx, k8sClient, sliceKey, tc.topology)
		})

		ginkgo.By("Checking that the Workload is admitted", func() {
			gomega.Eventually(func(g gomega.Gomega) {
				g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(createdWorkload), createdWorkload)).Should(gomega.Succeed())
				g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeTrue())
			}, utils.LongTimeout, utils.Timeout).Should(gomega.Succeed())
		})

		ginkgo.By("Deleting LeaderWorkerSet", func() {
			gomega.Expect(utils.DeleteAllLeaderWorkerSetsInNamespace(ctx, k8sClient, ns)).Should(gomega.Succeed())
		})

		ginkgo.By("Checking that Slice is deleted", func() {
			utils.ExpectObjectToBeDeleted(ctx, k8sClient, createdSlice, false)
		})
	},
		ginkgo.Entry("2x2x1 topology without leader", testCase{
			topology:        "2x2x1",
			size:            1,
			wantPartitionID: "f1",
			withLeader:      false,
		}),
		ginkgo.Entry("2x2x2 topology without leader", testCase{
			topology:        "2x2x2",
			size:            2,
			wantPartitionID: "e2",
			withLeader:      false,
		}),
		ginkgo.Entry("2x2x2 topology with leader", testCase{
			topology:        "2x2x2",
			size:            3, // 2 workers + 1 leader that does not require TPUs
			wantPartitionID: "e2",
			withLeader:      true,
		}),
		ginkgo.Entry("2x2x4 topology without leader", testCase{
			topology:        "2x2x4",
			size:            4,
			wantPartitionID: "d2",
			withLeader:      false,
		}),
		ginkgo.Entry("2x2x4 topology with leader", testCase{
			topology:        "2x2x4",
			size:            5, // 4 workers + 1 leader that does not require TPUs
			wantPartitionID: "d2",
			withLeader:      true,
		}),
		ginkgo.Entry("2x4x4 topology without leader", testCase{
			topology:        "2x4x4",
			size:            8,
			wantPartitionID: "c2",
			withLeader:      false,
		}),
		ginkgo.Entry("2x4x4 topology with leader", testCase{
			topology:        "2x4x4",
			size:            9, // 8 workers + 1 leader that does not require TPUs
			wantPartitionID: "c2",
			withLeader:      true,
		}),
	)
})
