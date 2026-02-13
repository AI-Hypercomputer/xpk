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
	"github.com/onsi/ginkgo/v2"
	"github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/types"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta2"
	jobsetcontroller "sigs.k8s.io/kueue/pkg/controller/jobs/jobset"
	"sigs.k8s.io/kueue/pkg/workload"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/controller"
	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/util/testing"
	testingjobsjobset "tpu-slice-controller/internal/util/testingjobs/jobset"
	"tpu-slice-controller/test/utils"
)

var _ = ginkgo.Describe("Subslicing", func() {
	var (
		topology *kueue.Topology
		ns       *corev1.Namespace
		rf       *kueue.ResourceFlavor
		ac       *kueue.AdmissionCheck
		cq       *kueue.ClusterQueue
		lq       *kueue.LocalQueue
	)

	ginkgo.BeforeEach(func() {
		ns = testing.MakeNamespaceWithGenerateName("e2e-subslicing-")
		utils.MustCreate(ctx, k8sClient, ns)

		topology = testing.MakeTopology("topology-subslicing").
			Levels("cloud.google.com/gce-topology-block",
				core.TPUSubBlockLabel,
				"cloud.google.com/gke-tpu-partition-2x4x4-id",
				"cloud.google.com/gke-tpu-partition-2x2x4-id",
				"cloud.google.com/gke-tpu-partition-2x2x2-id",
				"cloud.google.com/gke-tpu-partition-2x2x1-id",
				"kubernetes.io/hostname").
			Obj()
		utils.MustCreate(ctx, k8sClient, topology)

		rf = testing.MakeResourceFlavor("rf-subslicing").
			NodeLabel(nodeGroupLabel, nodeGroup).
			TopologyName(topology.Name).
			Obj()
		utils.MustCreate(ctx, k8sClient, rf)

		ac = testing.MakeAdmissionCheck("ac-subslicing").ControllerName(controller.SliceControllerName).Obj()
		utils.MustCreate(ctx, k8sClient, ac)

		cq = testing.MakeClusterQueue("cq-subslicing").
			AdmissionChecks(ac.Name).
			ResourceGroup(*testing.MakeFlavorQuotas(rf.Name).
				Resource(extraResource, "9999").
				Obj()).
			Obj()
		utils.MustCreate(ctx, k8sClient, cq)

		lq = testing.MakeLocalQueue("lq-subslicing", ns.Name).ClusterQueue(cq.Name).Obj()
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
		parallelism     int32
		wantPartitionID string
	}

	ginkgo.DescribeTable("should create Slice for", func(tc testCase) {
		jobSet := testingjobsjobset.MakeJobSet("jobset-"+tc.topology, ns.Name).
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
						core.TPUSliceTopologyAnnotation: tc.topology,
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
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
		sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1", 0)

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
				g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
				g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeTrue())
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
		ginkgo.Entry("2x2x1 topology", testCase{
			topology:        "2x2x1",
			parallelism:     1,
			wantPartitionID: "f1",
		}),
		ginkgo.Entry("2x2x2 topology", testCase{
			topology:        "2x2x2",
			parallelism:     2,
			wantPartitionID: "e1",
		}),
		ginkgo.Entry("2x2x4 topology", testCase{
			topology:        "2x2x4",
			parallelism:     4,
			wantPartitionID: "d1",
		}),
		ginkgo.Entry("2x4x4 topology", testCase{
			topology:        "2x4x4",
			parallelism:     8,
			wantPartitionID: "c1",
		}),
	)

	ginkgo.Describe("Multiple Replicas", func() {
		ginkgo.It("should create Slices for 2 replicas of 2x2x1 topology", func() {
			topology := "2x2x1"
			replicas := int32(2)
			parallelism := int32(4)
			possiblePartitions := []string{"f1", "f2", "f3", "f4"}

			jobSet := testingjobsjobset.MakeJobSet("jobset-multi-replicas", ns.Name).
				Queue(lq.Name).
				ReplicatedJobs(
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj1",
						Image:       utils.E2eTestAgnHostImage,
						Args:        utils.BehaviorWaitForDeletion,
						Replicas:    replicas,
						Parallelism: parallelism,
						Completions: parallelism,
						PodAnnotations: map[string]string{
							core.TPUSliceTopologyAnnotation: topology,
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
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

			var assignedPartitions []string
			for i := int32(0); i < replicas; i++ {
				createdSlice := &slice.Slice{}
				sliceKey := core.SliceKeyFromWorkload(createdWorkload, "rj1", i)

				ginkgo.By("Checking that SubSlice is created with correct partition", func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
						g.Expect(createdSlice.Spec.PartitionIds).To(gomega.HaveLen(1))
						g.Expect(possiblePartitions).To(gomega.ContainElement(createdSlice.Spec.PartitionIds[0]))
						g.Expect(createdSlice.Spec.Topology).To(gomega.Equal(topology))
					}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
				})
				assignedPartitions = append(assignedPartitions, createdSlice.Spec.PartitionIds[0])

				ginkgo.By("Adding Ready condition", func() {
					utils.SetSliceReady(ctx, k8sClient, sliceKey, topology)
				})
			}
			ginkgo.By("Checking that replicas got different partitions", func() {
				gomega.Expect(assignedPartitions).To(gomega.HaveLen(int(replicas)))
				gomega.Expect(assignedPartitions[0]).ToNot(gomega.Equal(assignedPartitions[1]))
			})

			ginkgo.By("Checking that the Workload is admitted", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeTrue())
				}, utils.LongTimeout, utils.Timeout).Should(gomega.Succeed())
			})
		})
	})

	ginkgo.Describe("Multiple Replicated Jobs", func() {
		ginkgo.It("should create Slices for 2 replicated jobs of 2x2x1 topology", func() {
			topology := "2x2x1"
			parallelism := int32(4)
			possiblePartitions := []string{"f1", "f2", "f3", "f4"}

			jobSet := testingjobsjobset.MakeJobSet("jobset-multi-rjs", ns.Name).
				Queue(lq.Name).
				ReplicatedJobs(
					testingjobsjobset.ReplicatedJobRequirements{
						Name:        "rj1",
						Image:       utils.E2eTestAgnHostImage,
						Args:        utils.BehaviorWaitForDeletion,
						Replicas:    1,
						Parallelism: parallelism,
						Completions: parallelism,
						PodAnnotations: map[string]string{
							core.TPUSliceTopologyAnnotation: topology,
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
						Parallelism: parallelism,
						Completions: parallelism,
						PodAnnotations: map[string]string{
							core.TPUSliceTopologyAnnotation: topology,
						},
						NodeSelector: map[string]string{
							"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
						},
					},
				).
				RequestAndLimit("rj1", extraResource, "1").
				RequestAndLimit("rj2", extraResource, "1").
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

			var assignedPartitions []string
			for _, rjName := range []string{"rj1", "rj2"} {
				createdSlice := &slice.Slice{}
				sliceKey := core.SliceKeyFromWorkload(createdWorkload, kueue.PodSetReference(rjName), 0)

				ginkgo.By("Checking that Slice is created with correct partition for "+rjName, func() {
					gomega.Eventually(func(g gomega.Gomega) {
						g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
						g.Expect(createdSlice.Spec.PartitionIds).To(gomega.HaveLen(1))
						g.Expect(possiblePartitions).To(gomega.ContainElement(createdSlice.Spec.PartitionIds[0]))
						g.Expect(createdSlice.Spec.Topology).To(gomega.Equal(topology))
					}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
				})
				assignedPartitions = append(assignedPartitions, createdSlice.Spec.PartitionIds[0])

				ginkgo.By("Adding Ready condition for "+rjName, func() {
					utils.SetSliceReady(ctx, k8sClient, sliceKey, topology)
				})
			}
			ginkgo.By("Checking that replicated jobs got different partitions", func() {
				gomega.Expect(assignedPartitions).To(gomega.HaveLen(2))
				gomega.Expect(assignedPartitions[0]).ToNot(gomega.Equal(assignedPartitions[1]))
			})

			ginkgo.By("Checking that the Workload is admitted", func() {
				gomega.Eventually(func(g gomega.Gomega) {
					g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
					g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeTrue())
				}, utils.LongTimeout, utils.Timeout).Should(gomega.Succeed())
			})
		})
	})
})
