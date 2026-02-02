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

	ginkgo.It("should create Slice for 2x2x1 topology", func() {
		ginkgo.By("Labeling nodes with partition ID", func() {
			nodes := &corev1.NodeList{}
			gomega.Expect(k8sClient.List(ctx, nodes)).To(gomega.Succeed())
			for _, node := range nodes.Items {
				patch := client.MergeFrom(node.DeepCopy())
				node.Labels["cloud.google.com/gke-tpu-partition-2x2x1-id"] = "partition1"
				gomega.Expect(k8sClient.Patch(ctx, &node, patch)).To(gomega.Succeed())
			}
		})
		ginkgo.DeferCleanup(func() {
			nodes := &corev1.NodeList{}
			gomega.Expect(k8sClient.List(ctx, nodes)).To(gomega.Succeed())
			for _, node := range nodes.Items {
				patch := client.MergeFrom(node.DeepCopy())
				delete(node.Labels, "cloud.google.com/gke-tpu-partition-2x2x1-id")
				gomega.Expect(k8sClient.Patch(ctx, &node, patch)).To(gomega.Succeed())
			}
		})

		jobSet := testingjobsjobset.MakeJobSet("jobset-2x2x1", ns.Name).
			Queue(lq.Name).
			ReplicatedJobs(
				testingjobsjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Image:       utils.E2eTestAgnHostImage,
					Args:        utils.BehaviorWaitForDeletion,
					Replicas:    1,
					Parallelism: 4,
					Completions: 4,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "2x2x1",
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

		ginkgo.By("Checking that Slice is created with correct partition", func() {
			gomega.Eventually(func(g gomega.Gomega) {
				g.Expect(k8sClient.Get(ctx, sliceKey, createdSlice)).To(gomega.Succeed())
				g.Expect(createdSlice.Spec.PartitionIds).To(gomega.ContainElement("partition1"))
				g.Expect(createdSlice.Spec.Topology).To(gomega.Equal("2x2x1"))
			}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
		})

		ginkgo.By("Adding Ready condition", func() {
			utils.SetSliceReady(ctx, k8sClient, sliceKey, "2x2x1")
		})

		ginkgo.By("Checking that the Workload is admitted", func() {
			gomega.Eventually(func(g gomega.Gomega) {
				g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
				g.Expect(workload.IsAdmitted(createdWorkload)).Should(gomega.BeTrue())
			}, utils.LongTimeout, utils.Timeout).Should(gomega.Succeed())
		})
	})
})
