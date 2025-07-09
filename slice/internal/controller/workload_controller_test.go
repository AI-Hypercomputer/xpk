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
	"github.com/google/go-cmp/cmp/cmpopts"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	slice "tpu-slice-controller/api/v1alpha1"
	utiltesting "tpu-slice-controller/internal/util/testing"
)

var (
	baseCmpOpts = cmp.Options{
		cmpopts.EquateEmpty(),
		cmpopts.IgnoreFields(metav1.ObjectMeta{}, "ResourceVersion"),
		cmpopts.IgnoreFields(metav1.Condition{}, "LastTransitionTime"),
	}
)

func TestWorkloadReconciler(t *testing.T) {
	const (
		baseWorkloadName                     = "workload"
		basePodSet1Name                      = "ps1"
		basePodSet2Name                      = "ps2"
		baseAcceleratorType                  = "tpu-v4-podslice"
		baseAcceleratorTopology              = "2x2x2"
		baseTPUReservationSubBlockLabelValue = "tpu-subblock-1"
		baseNodePoolLabelValue               = "tpu-v4-pool"
	)
	baseRequest := types.NamespacedName{Name: baseWorkloadName, Namespace: corev1.NamespaceDefault}
	baseWorkloadWrapper := utiltesting.MakeWorkload(baseWorkloadName, corev1.NamespaceDefault).UID(baseWorkloadName)
	basePodSet1Wrapper := utiltesting.MakePodSet(basePodSet1Name)
	basePodSet2Wrapper := utiltesting.MakePodSet(basePodSet2Name)
	basePodSetAssignment1Wrapper := utiltesting.MakePodSetAssignment(basePodSet1Name)
	basePodSetAssignment2Wrapper := basePodSetAssignment1Wrapper.Clone().
		Name(basePodSet2Name)
	baseSlice1Wrapper := utiltesting.MakeSliceWrapper(GetSliceName(baseWorkloadName, basePodSet1Name), corev1.NamespaceDefault).
		ControllerReference(kueue.GroupVersion.WithKind("Workload"), baseWorkloadName, baseWorkloadName).
		AcceleratorType(baseAcceleratorType).
		AcceleratorTopology(baseAcceleratorTopology)
	baseSlice2Wrapper := baseSlice1Wrapper.Clone().
		Name(GetSliceName(baseWorkloadName, basePodSet2Name))

	cases := map[string]struct {
		request       types.NamespacedName
		objs          []client.Object
		wantWorkloads []kueue.Workload
		wantSlices    []slice.Slice
		wantErr       error
	}{
		"should skip reconciliation because the Workload was not found": {
			request: types.NamespacedName{Name: "other-workload", Namespace: corev1.NamespaceDefault},
			objs: []client.Object{
				baseWorkloadWrapper.DeepCopy(),
				baseSlice1Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.DeepCopy()},
			wantSlices:    []slice.Slice{*baseSlice1Wrapper.DeepCopy()},
		},
		"should delete the finalizer because the Workload has a DeletionTimestamp": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					DeletionTimestamp(time.Now()).
					Finalizers(CleanupSliceFinalizerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
			},
		},
		"should delete finalizer because Workload is finished": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().Finalizers(CleanupSliceFinalizerName).Finished().Obj(),
				baseSlice1Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().Finished().Obj()},
		},
		"should delete finalizer because Workload is evicted": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().Finalizers(CleanupSliceFinalizerName).Evicted().Obj(),
				baseSlice1Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().Evicted().Obj()},
		},
		"should delete finalizer because Workload is deactivated": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().Finalizers(CleanupSliceFinalizerName).Active(false).Obj(),
				baseSlice1Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().Active(false).Obj()},
		},
		"should add finalizer": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					Obj(),
			},
		},
		"shouldn't create Slices because wl.Status.Admission is nil": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					Obj(),
			},
		},
		"shouldn't create Slices because there are no PodSetAssignments": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Admission(&kueue.Admission{}).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					Admission(&kueue.Admission{}).
					Obj(),
			},
		},
		"shouldn't create Slice because PodSet not found": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					PodSetAssignments(*basePodSetAssignment1Wrapper.DeepCopy()).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					PodSetAssignments(*basePodSetAssignment1Wrapper.DeepCopy()).
					Obj(),
			},
			wantErr: errPodSetNotFound,
		},
		"shouldn't create Slice because TPUTopologyLabel label not found": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					PodSets(*basePodSet1Wrapper.DeepCopy()).
					PodSetAssignments(*basePodSetAssignment1Wrapper.DeepCopy()).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					PodSets(*basePodSet1Wrapper.DeepCopy()).
					PodSetAssignments(*basePodSetAssignment1Wrapper.DeepCopy()).
					Obj(),
			},
		},
		"shouldn't create Slice because TPUAcceleratorLabel label not found": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					PodSets(*basePodSet1Wrapper.Clone().
						NodeSelector(TPUTopologyLabel, "2x2x1").
						Obj()).
					PodSetAssignments(*basePodSetAssignment1Wrapper.DeepCopy()).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					PodSets(*basePodSet1Wrapper.Clone().
						NodeSelector(TPUTopologyLabel, "2x2x1").
						Obj()).
					PodSetAssignments(*basePodSetAssignment1Wrapper.DeepCopy()).
					Obj(),
			},
		},
		"shouldn't create Slice because TopologyAssignment not found": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					PodSets(*basePodSet1Wrapper.Clone().
						NodeSelector(TPUTopologyLabel, "2x2x1").
						NodeSelector(TPUAcceleratorLabel, "tpu-v4-podslice").
						Obj()).
					PodSetAssignments(*basePodSetAssignment1Wrapper.DeepCopy()).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					PodSets(*basePodSet1Wrapper.Clone().
						NodeSelector(TPUTopologyLabel, "2x2x1").
						NodeSelector(TPUAcceleratorLabel, "tpu-v4-podslice").
						Obj()).
					PodSetAssignments(*basePodSetAssignment1Wrapper.DeepCopy()).
					Obj(),
			},
		},
		"should create Slice with unique domains": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					PodSets(*basePodSet1Wrapper.Clone().
						NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
						NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
						Obj()).
					PodSetAssignments(*basePodSetAssignment1Wrapper.Clone().
						TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
							{Values: []string{"domain1", "domain2", "domain2"}, Count: 2},
						}).
						Obj()).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					PodSets(*basePodSet1Wrapper.Clone().
						NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
						NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
						Obj()).
					PodSetAssignments(*basePodSetAssignment1Wrapper.Clone().
						TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
							{Values: []string{"domain1", "domain2", "domain2"}, Count: 2},
						}).
						Obj()).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.DeepCopy(),
			},
		},
		"should create Slices": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					PodSets(
						*basePodSet1Wrapper.Clone().
							NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
							NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
							NodeSelector(TPUReservationSubBlockLabel, baseTPUReservationSubBlockLabelValue).
							Obj(),
						*basePodSet2Wrapper.Clone().
							NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
							NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
							NodeSelector(NodePoolLabel, baseNodePoolLabelValue).
							Obj(),
					).
					PodSetAssignments(
						*basePodSetAssignment1Wrapper.Clone().
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{Values: []string{"domain1", "domain2"}, Count: 2},
							}).
							Obj(),
						*basePodSetAssignment2Wrapper.Clone().
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{Values: []string{"domain1", "domain2"}, Count: 2},
							}).
							Obj(),
					).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					PodSets(
						*basePodSet1Wrapper.Clone().
							NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
							NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
							NodeSelector(TPUReservationSubBlockLabel, baseTPUReservationSubBlockLabelValue).
							Obj(),
						*basePodSet2Wrapper.Clone().
							NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
							NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
							NodeSelector(NodePoolLabel, baseNodePoolLabelValue).
							Obj(),
					).
					PodSetAssignments(
						*basePodSetAssignment1Wrapper.Clone().
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{Values: []string{"domain1", "domain2"}, Count: 2},
							}).
							Obj(),
						*basePodSetAssignment2Wrapper.Clone().
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{Values: []string{"domain1", "domain2"}, Count: 2},
							}).
							Obj(),
					).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().
					NodeSelector(map[string][]string{
						TPUReservationSubBlockLabel: {"domain1", "domain2"},
					}).
					Obj(),
				*baseSlice2Wrapper.Clone().
					NodeSelector(map[string][]string{
						NodePoolLabel: {"domain1", "domain2"},
					}).
					Obj(),
			},
		},
		"should create Slice with NodePoolLabel and TPUReservationSubBlock labels": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					PodSets(*basePodSet1Wrapper.Clone().
						NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
						NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
						NodeSelector(TPUReservationSubBlockLabel, baseTPUReservationSubBlockLabelValue).
						NodeSelector(NodePoolLabel, baseNodePoolLabelValue).
						Obj()).
					PodSetAssignments(*basePodSetAssignment1Wrapper.Clone().
						TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
							{Values: []string{"domain1", "domain2"}, Count: 2},
						}).
						Obj()).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					PodSets(*basePodSet1Wrapper.Clone().
						NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
						NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
						NodeSelector(TPUReservationSubBlockLabel, baseTPUReservationSubBlockLabelValue).
						NodeSelector(NodePoolLabel, baseNodePoolLabelValue).
						Obj()).
					PodSetAssignments(*basePodSetAssignment1Wrapper.Clone().
						TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
							{Values: []string{"domain1", "domain2"}, Count: 2},
						}).
						Obj()).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().
					NodeSelector(map[string][]string{
						TPUReservationSubBlockLabel: {"domain1", "domain2"},
						NodePoolLabel:               {"domain1", "domain2"},
					}).
					Obj(),
			},
		},
		"should create missing Slices": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					PodSets(
						*basePodSet1Wrapper.Clone().
							NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
							NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
							NodeSelector(TPUReservationSubBlockLabel, baseTPUReservationSubBlockLabelValue).
							Obj(),
						*basePodSet2Wrapper.Clone().
							NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
							NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
							NodeSelector(NodePoolLabel, baseNodePoolLabelValue).
							Obj(),
					).
					PodSetAssignments(
						*basePodSetAssignment1Wrapper.Clone().
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{Values: []string{"domain1", "domain2"}, Count: 2},
							}).
							Obj(),
						*basePodSetAssignment2Wrapper.Clone().
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{Values: []string{"domain1", "domain2"}, Count: 2},
							}).
							Obj(),
					).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					PodSets(
						*basePodSet1Wrapper.Clone().
							NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
							NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
							NodeSelector(TPUReservationSubBlockLabel, baseTPUReservationSubBlockLabelValue).
							Obj(),
						*basePodSet2Wrapper.Clone().
							NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
							NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
							NodeSelector(NodePoolLabel, baseNodePoolLabelValue).
							Obj(),
					).
					PodSetAssignments(
						*basePodSetAssignment1Wrapper.Clone().
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{Values: []string{"domain1", "domain2"}, Count: 2},
							}).
							Obj(),
						*basePodSetAssignment2Wrapper.Clone().
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{Values: []string{"domain1", "domain2"}, Count: 2},
							}).
							Obj(),
					).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.DeepCopy(),
				*baseSlice2Wrapper.Clone().
					NodeSelector(map[string][]string{
						NodePoolLabel: {"domain1", "domain2"},
					}).
					Obj(),
			},
		},
		"should delete redundant Slices": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					PodSets(
						*basePodSet1Wrapper.Clone().
							NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
							NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
							NodeSelector(TPUReservationSubBlockLabel, baseTPUReservationSubBlockLabelValue).
							Obj(),
					).
					PodSetAssignments(
						*basePodSetAssignment1Wrapper.Clone().
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{Values: []string{"domain1", "domain2"}, Count: 2},
							}).
							Obj(),
					).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					PodSets(
						*basePodSet1Wrapper.Clone().
							NodeSelector(TPUTopologyLabel, baseAcceleratorTopology).
							NodeSelector(TPUAcceleratorLabel, baseAcceleratorType).
							NodeSelector(TPUReservationSubBlockLabel, baseTPUReservationSubBlockLabelValue).
							Obj(),
					).
					PodSetAssignments(
						*basePodSetAssignment1Wrapper.Clone().
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{Values: []string{"domain1", "domain2"}, Count: 2},
							}).
							Obj(),
					).
					Obj(),
			},
			wantSlices: []slice.Slice{*baseSlice1Wrapper.DeepCopy()},
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			scheme := runtime.NewScheme()
			utilruntime.Must(kueue.AddToScheme(scheme))
			utilruntime.Must(slice.AddToScheme(scheme))

			ctx, _ := utiltesting.ContextWithLog(t)
			clientBuilder := fake.NewClientBuilder().WithScheme(scheme).WithStatusSubresource(&kueue.Workload{})

			indexer := utiltesting.AsIndexer(clientBuilder)
			if err := SetupIndexer(ctx, indexer); err != nil {
				t.Fatalf("Setup failed: %v", err)
			}

			kClient := clientBuilder.WithObjects(tc.objs...).Build()
			reconciler := NewWorkloadReconciler(kClient)

			_, err := reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: tc.request})
			if diff := cmp.Diff(tc.wantErr, err, cmpopts.EquateErrors()); diff != "" {
				t.Errorf("Error after reconcile (-want,+got):\n%s", diff)
			}

			workloads := &kueue.WorkloadList{}
			err = kClient.List(ctx, workloads)
			if err != nil {
				t.Errorf("Error listing workloads: %v", err)
			}
			if diff := cmp.Diff(tc.wantWorkloads, workloads.Items, baseCmpOpts); diff != "" {
				t.Errorf("Workloads after reconcile (-want,+got):\n%s", diff)
			}

			slices := &slice.SliceList{}
			err = kClient.List(ctx, slices)
			if err != nil {
				t.Errorf("Error listing slices: %v", err)
			}
			if diff := cmp.Diff(tc.wantSlices, slices.Items, baseCmpOpts); diff != "" {
				t.Errorf("Slices after reconcile (-want,+got):\n%s", diff)
			}
		})
	}
}
