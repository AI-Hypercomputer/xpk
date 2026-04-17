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
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta2"
	jobcontroller "sigs.k8s.io/kueue/pkg/controller/jobs/job"
	"sigs.k8s.io/kueue/pkg/workload"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/controller"
	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/util/testing"
	testingjobs "tpu-slice-controller/internal/util/testingjobs/job"
	"tpu-slice-controller/test/utils"
)

var _ = ginkgo.Describe("Job Subslicing", func() {
	var (
		topology *kueue.Topology
		ns       *corev1.Namespace
		rf       *kueue.ResourceFlavor
		ac       *kueue.AdmissionCheck
		cq       *kueue.ClusterQueue
		lq       *kueue.LocalQueue
	)

	ginkgo.BeforeEach(func() {
		ns = testing.MakeNamespaceWithGenerateName("e2e-job-subslicing-")
		utils.MustCreate(ctx, k8sClient, ns)

		topology = testing.MakeTopology("topology-job-subslicing").
			Levels("cloud.google.com/gce-topology-block",
				core.TPUSubBlockLabel,
				"cloud.google.com/gke-tpu-partition-2x4x4-id",
				"cloud.google.com/gke-tpu-partition-2x2x4-id",
				"cloud.google.com/gke-tpu-partition-2x2x2-id",
				"cloud.google.com/gke-tpu-partition-2x2x1-id",
				"kubernetes.io/hostname").
			Obj()
		utils.MustCreate(ctx, k8sClient, topology)

		rf = testing.MakeResourceFlavor("rf-job-subslicing").
			NodeLabel(nodeGroupLabel, nodeGroup).
			TopologyName(topology.Name).
			Obj()
		utils.MustCreate(ctx, k8sClient, rf)

		ac = testing.MakeAdmissionCheck("ac-job-subslicing").ControllerName(controller.SliceControllerName).Obj()
		utils.MustCreate(ctx, k8sClient, ac)

		cq = testing.MakeClusterQueue("cq-job-subslicing").
			AdmissionChecks(ac.Name).
			ResourceGroup(*testing.MakeFlavorQuotas(rf.Name).
				Resource(core.TPUResourceName, "9999").
				Obj()).
			Obj()
		utils.MustCreate(ctx, k8sClient, cq)

		lq = testing.MakeLocalQueue("lq-job-subslicing", ns.Name).ClusterQueue(cq.Name).Obj()
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
		job := testingjobs.MakeJob("job", ns.Name).
			Queue(lq.Name).
			Image(utils.E2eTestAgnHostImage).
			Args(utils.BehaviorWaitForDeletion...).
			Parallelism(tc.parallelism).
			Completions(tc.parallelism).
			Indexed(true).
			PodAnnotation(core.TPUSliceTopologyAnnotation, tc.topology).
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
				g.Expect(annotations["kueue.x-k8s.io/podset-required-topology"]).
					Should(gomega.Equal("cloud.google.com/gce-topology-block"))
				g.Expect(annotations["kueue.x-k8s.io/podset-slice-required-topology"]).
					Should(gomega.Equal(fmt.Sprintf("cloud.google.com/gke-tpu-partition-%s-id", tc.topology)))
				g.Expect(annotations["kueue.x-k8s.io/podset-slice-size"]).
					Should(gomega.Equal(fmt.Sprint(tc.parallelism)))

				// node health
				affinity := createdJob.Spec.Template.Spec.Affinity
				g.Expect(affinity).ShouldNot(gomega.BeNil())
				g.Expect(affinity.NodeAffinity).ShouldNot(gomega.BeNil())
				g.Expect(affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution).ShouldNot(gomega.BeNil())
				found := false
				for _, term := range affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms {
					for _, matchExpression := range term.MatchExpressions {
						if matchExpression.Key == fmt.Sprintf("cloud.google.com/gke-tpu-partition-%s-state", tc.topology) {
							found = true
							g.Expect(matchExpression.Operator).Should(gomega.Equal(corev1.NodeSelectorOpIn))
							g.Expect(matchExpression.Values).Should(gomega.ConsistOf(core.TPUSliceHealthNodeSelectorHealthy, core.TPUSliceHealthNodeSelectorDegraded))
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

		ginkgo.By("Waiting for Admission of the Workload", func() {
			gomega.Eventually(func(g gomega.Gomega) {
				g.Expect(k8sClient.Get(ctx, wlKey, createdWorkload)).Should(gomega.Succeed())
				g.Expect(createdWorkload.Status.Admission).ShouldNot(gomega.BeNil())
			}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
		})

		createdSlice := &slice.Slice{}
		sliceKey := core.SliceKeyFromWorkload(createdWorkload, "main", 0)

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

		ginkgo.By("Deleting Job", func() {
			gomega.Expect(utils.DeleteAllJobsInNamespace(ctx, k8sClient, ns)).Should(gomega.Succeed())
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
			wantPartitionID: "e2",
		}),
		ginkgo.Entry("2x2x4 topology", testCase{
			topology:        "2x2x4",
			parallelism:     4,
			wantPartitionID: "d2",
		}),
		ginkgo.Entry("2x4x4 topology", testCase{
			topology:        "2x4x4",
			parallelism:     8,
			wantPartitionID: "c2",
		}),
	)
})
