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

package controller

import (
	"testing"
	"time"

	"github.com/google/go-cmp/cmp"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	testingclock "k8s.io/utils/clock/testing"
	"k8s.io/utils/ptr"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/client/interceptor"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta2"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/core"
	utiltesting "tpu-slice-controller/internal/util/testing"
	utiltestingjobsjobset "tpu-slice-controller/internal/util/testingjobs/jobset"
)

func TestReproduction(t *testing.T) {
	const (
		baseACName       = "ac"
		baseJobSetName   = "jobset"
		baseWorkloadName = "workload"
	)

	now := time.Now().Truncate(time.Second)

	buildAdmissionCheckState := func(state kueue.CheckState, message string) kueue.AdmissionCheckState {
		return kueue.AdmissionCheckState{
			Name:               baseACName,
			State:              state,
			LastTransitionTime: metav1.NewTime(now),
			Message:            message,
		}
	}

	baseRequest := types.NamespacedName{Name: baseWorkloadName, Namespace: corev1.NamespaceDefault}
	baseJobSetWrapper := utiltestingjobsjobset.MakeJobSet(baseJobSetName, corev1.NamespaceDefault)
	baseAdmissionCheckWrapper := utiltesting.MakeAdmissionCheck(baseACName).ControllerName(SliceControllerName)

	baseLevels := []string{"kubernetes.io/hostname"}

	baseWorkloadWrapper := utiltesting.MakeWorkload(baseWorkloadName, corev1.NamespaceDefault).
		UID(baseWorkloadName).
		AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, ""))

	baseSlice1Wrapper := utiltesting.MakeSliceWrapper(core.SliceName(corev1.NamespaceDefault, baseWorkloadName, "ps1", 0)).
		Type(slice.TypeTpu7x).
		Topology("4x4x12").
		OwnerWorkloadAnnotations(corev1.NamespaceDefault, baseWorkloadName).
		PartitionIDs("subblock1")

	worker1Node := utiltesting.MakeNode("worker1").Label(core.TPUSubBlockLabel, "subblock1")

	testCases := map[string]struct {
		objs        []client.Object
		wantJobSets []jobset.JobSet
	}{
		"should not set empty nodeSelector for irrelevant replicated job": {
			objs: []client.Object{
				worker1Node.DeepCopy(),
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(
						*utiltesting.MakePodSet("ps1", 2, ptr.To(int32(1))).
							Annotation(core.TPUSliceTopologyAnnotation, "4x4x12").
							NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
							Obj(),
						*utiltesting.MakePodSet("ps2", 2, ptr.To(int32(1))).
							Obj(),
					).
					ReserveQuota(&kueue.Admission{
						PodSetAssignments: []kueue.PodSetAssignment{
							utiltesting.MakePodSetAssignment("ps1").
								TopologyAssignment(baseLevels, []kueue.TopologyAssignmentSlice{
									utiltesting.MakeTopologyAssignmentSlice(1, []int32{2}).
										Value("worker1").
										Obj(),
								}).Obj(),
							utiltesting.MakePodSetAssignment("ps2").Obj(),
						},
					}, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
				baseJobSetWrapper.Clone().ReplicatedJobs(
					utiltestingjobsjobset.ReplicatedJobRequirements{
						Name:           "ps1",
						PodAnnotations: map[string]string{core.TPUSliceTopologyAnnotation: "4x4x12"},
						NodeSelector:   map[string]string{"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x)},
					},
					utiltestingjobsjobset.ReplicatedJobRequirements{
						Name: "ps2",
					},
				).Obj(),
				baseSlice1Wrapper.Clone().Active().Obj(),
			},
			wantJobSets: []jobset.JobSet{*baseJobSetWrapper.Clone().ReplicatedJobs(
				utiltestingjobsjobset.ReplicatedJobRequirements{
					Name: "ps1",
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "4x4x12",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
						core.TPUTopologyAnnotation:             "4x4x12",
					},
				},
				utiltestingjobsjobset.ReplicatedJobRequirements{
					Name: "ps2",
				},
			).Obj()},
		},
	}
	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			scheme := runtime.NewScheme()
			utilruntime.Must(corev1.AddToScheme(scheme))
			utilruntime.Must(jobset.AddToScheme(scheme))
			utilruntime.Must(kueue.AddToScheme(scheme))
			utilruntime.Must(slice.AddToScheme(scheme))

			interceptorFuncs := interceptor.Funcs{
				SubResourcePatch: treatSSAAsStrategicMerge,
				Patch:            treatSSAAsStrategicMergePatch,
			}

			ctx, _ := utiltesting.ContextWithLog(t)
			clientBuilder := fake.NewClientBuilder().WithScheme(scheme).
				WithStatusSubresource(&kueue.Workload{}).
				WithObjects(tc.objs...).
				WithInterceptorFuncs(interceptorFuncs)

			indexer := utiltesting.AsIndexer(clientBuilder)
			if err := SetupIndexer(ctx, indexer); err != nil {
				t.Fatalf("Setup failed: %v", err)
			}

			kClient := clientBuilder.Build()
			recorder := &utiltesting.EventRecorder{}
			reconciler := NewWorkloadReconciler(kClient, recorder, 3*time.Minute)
			reconciler.clock = testingclock.NewFakeClock(now)

			_, err := reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: baseRequest})
			if err != nil {
				t.Errorf("Reconcile failed: %v", err)
			}

			jobSets := &jobset.JobSetList{}
			err = kClient.List(ctx, jobSets)
			if err != nil {
				t.Errorf("Error listing jobsets: %v", err)
			}
			if diff := cmp.Diff(tc.wantJobSets, jobSets.Items, baseCmpOpts); diff != "" {
				t.Errorf("JobSets after reconcile (-want,+got):\n%s", diff)
			}
		})
	}
}
