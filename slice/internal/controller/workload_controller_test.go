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
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	"k8s.io/client-go/util/workqueue"
	testingclock "k8s.io/utils/clock/testing"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/client/interceptor"
	"sigs.k8s.io/controller-runtime/pkg/controller/priorityqueue"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	slice "tpu-slice-controller/api/v1alpha1"
	"tpu-slice-controller/internal/core"
	utiltesting "tpu-slice-controller/internal/util/testing"
)

var (
	baseCmpOpts = cmp.Options{
		cmpopts.EquateEmpty(),
		cmpopts.IgnoreFields(metav1.ObjectMeta{}, "ResourceVersion"),
		cmpopts.IgnoreFields(metav1.Condition{}, "LastTransitionTime"),
	}
	errTest = errors.New("test error")
)

func TestWorkloadReconciler(t *testing.T) {
	now := time.Now().Truncate(time.Second)
	fakeClock := testingclock.NewFakeClock(now)

	baseWorkloadName := "workload"
	baseAdmissionCheckName := "ac"
	baseRequest := types.NamespacedName{Name: baseWorkloadName, Namespace: corev1.NamespaceDefault}
	baseAdmissionCheckWrapper := utiltesting.MakeAdmissionCheck(baseAdmissionCheckName).ControllerName(SliceControllerName)
	baseWorkloadWrapper := utiltesting.MakeWorkload(baseWorkloadName, corev1.NamespaceDefault).
		UID(types.UID(baseWorkloadName)).
		AdmissionCheck(kueue.AdmissionCheckState{
			Name:               kueue.AdmissionCheckReference(baseAdmissionCheckName),
			State:              kueue.CheckStatePending,
			LastTransitionTime: metav1.NewTime(now),
			Message:            "",
		})
	baseWorkloadWrapperWithPodSets := baseWorkloadWrapper.Clone().
		PodSets(
			*utiltesting.MakePodSet("ps1", 2).
				Annotation(core.TPUTopologyAnnotation, "4x4x12").
				NodeSelector(core.TPUAcceleratorLabel, "tpu-v7x").
				Obj(),
			*utiltesting.MakePodSet("ps2", 2).
				Annotation(core.TPUTopologyAnnotation, "4x4x12").
				NodeSelector(core.TPUAcceleratorLabel, "tpu-v7x").
				Obj(),
		)
	baseWorkloadWrapperWithAdmission := baseWorkloadWrapperWithPodSets.Clone().
		ReserveQuota(
			&kueue.Admission{
				PodSetAssignments: []kueue.PodSetAssignment{
					utiltesting.MakePodSetAssignment("ps1").
						TopologyAssignment([]string{core.TPUBlockLabel, core.TPUSubBlockLabel}, []kueue.TopologyDomainAssignment{
							{
								Values: []string{"block1", "subblock1"},
								Count:  2,
							},
						}).Obj(),
					utiltesting.MakePodSetAssignment("ps2").
						TopologyAssignment([]string{core.TPUBlockLabel, core.TPUSubBlockLabel}, []kueue.TopologyDomainAssignment{
							{
								Values: []string{"block1", "subblock2"},
								Count:  2,
							},
						}).
						Obj(),
				},
			}, now,
		)
	baseSliceWrapper := utiltesting.MakeSliceWrapper(baseWorkloadName, corev1.NamespaceDefault).
		ControllerReference(kueue.GroupVersion.WithKind("Workload"), baseWorkloadName, baseWorkloadName).
		NodeSelector(map[string][]string{TPUReservationSubblockLabel: {"subblock1", "subblock2"}})

	cases := map[string]struct {
		interceptorFuncsCreate func(ctx context.Context, client client.WithWatch, obj client.Object, opts ...client.CreateOption) error
		request                types.NamespacedName
		objs                   []client.Object
		wantWorkloads          []kueue.Workload
		wantSlices             []slice.Slice
		wantErr                error
		wantEvents             []utiltesting.EventRecord
	}{
		"should skip reconciliation because the Workload was not found": {
			request: types.NamespacedName{Name: "other-workload", Namespace: corev1.NamespaceDefault},
			objs: []client.Object{
				baseWorkloadWrapper.Clone().Finalizers(SliceControllerName).DeletionTimestamp(now).Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().Finalizers(SliceControllerName).DeletionTimestamp(now).Obj(),
			},
		},
		"should delete the finalizer because the Workload has a DeletionTimestamp": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().Finalizers(SliceControllerName).DeletionTimestamp(now).Obj(),
				baseSliceWrapper.DeepCopy(),
			},
		},
		"should delete the finalizer because the Workload is finished": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().Finalizers(SliceControllerName).Finished().Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().Finished().Obj()},
		},
		"should delete the finalizer because the Workload is evicted": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().Finalizers(SliceControllerName).Evicted().Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().Evicted().Obj()},
		},
		"should delete the finalizer because the Workload is deactivated": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().Finalizers(SliceControllerName).Active(false).Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().Active(false).Obj()},
		},
		"shouldn't add finalizer because invalid TPU topology annotation": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(
						*utiltesting.MakePodSet("ps", 2).
							Annotation(core.TPUTopologyAnnotation, "4x4").
							NodeSelector(core.TPUAcceleratorLabel, "tpu-v7x").
							Obj(),
					).
					ReserveQuota(
						&kueue.Admission{
							PodSetAssignments: []kueue.PodSetAssignment{
								utiltesting.MakePodSetAssignment("ps1").
									TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
										{
											Values: []string{"domain1", "domain2"},
											Count:  2,
										},
									}).Obj(),
							},
						}, now,
					).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(
						*utiltesting.MakePodSet("ps", 2).
							Annotation(core.TPUTopologyAnnotation, "4x4").
							NodeSelector(core.TPUAcceleratorLabel, "tpu-v7x").
							Obj(),
					).
					ReserveQuota(
						&kueue.Admission{
							PodSetAssignments: []kueue.PodSetAssignment{
								utiltesting.MakePodSetAssignment("ps1").
									TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
										{
											Values: []string{"domain1", "domain2"},
											Count:  2,
										},
									}).Obj(),
							},
						}, now,
					).
					Obj(),
			},
		},
		"shouldn't add finalizer because invalid TPU accelerator node selector": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(
						*utiltesting.MakePodSet("ps", 2).
							Annotation(core.TPUTopologyAnnotation, "4x4x12").
							NodeSelector(core.TPUAcceleratorLabel, "invalid").
							Obj(),
					).
					ReserveQuota(
						&kueue.Admission{
							PodSetAssignments: []kueue.PodSetAssignment{
								utiltesting.MakePodSetAssignment("ps1").
									TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
										{
											Values: []string{"domain1", "domain2"},
											Count:  2,
										},
									}).Obj(),
							},
						}, now,
					).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(
						*utiltesting.MakePodSet("ps", 2).
							Annotation(core.TPUTopologyAnnotation, "4x4x12").
							NodeSelector(core.TPUAcceleratorLabel, "invalid").
							Obj(),
					).
					ReserveQuota(
						&kueue.Admission{
							PodSetAssignments: []kueue.PodSetAssignment{
								utiltesting.MakePodSetAssignment("ps1").
									TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
										{
											Values: []string{"domain1", "domain2"},
											Count:  2,
										},
									}).Obj(),
							},
						}, now,
					).
					Obj(),
			},
		},
		"shouldn't add finalizer because there’s no Admission": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapperWithPodSets.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithPodSets.DeepCopy(),
			},
		},
		"shouldn't add finalizer because there’s no TopologyAssignment": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapperWithPodSets.Clone().
					ReserveQuota(
						&kueue.Admission{
							PodSetAssignments: []kueue.PodSetAssignment{
								utiltesting.MakePodSetAssignment("ps1").Obj(),
								utiltesting.MakePodSetAssignment("ps2").Obj(),
							},
						}, now,
					).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithPodSets.Clone().
					ReserveQuota(
						&kueue.Admission{
							PodSetAssignments: []kueue.PodSetAssignment{
								utiltesting.MakePodSetAssignment("ps1").Obj(),
								utiltesting.MakePodSetAssignment("ps2").Obj(),
							},
						}, now,
					).
					Obj(),
			},
		},
		"shouldn't add finalizer because there’s no AdmissionCheck": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapperWithAdmission.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithAdmission.DeepCopy(),
			},
		},
		"should add finalizer": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapperWithAdmission.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithAdmission.Clone().
					Finalizers(SliceControllerName).
					Obj(),
			},
		},
		"should create a Slice": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapperWithAdmission.Finalizers(SliceControllerName).DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithAdmission.Clone().
					Finalizers(SliceControllerName).
					AdmissionCheck(kueue.AdmissionCheckState{
						Name:               kueue.AdmissionCheckReference(baseAdmissionCheckName),
						State:              kueue.CheckStatePending,
						LastTransitionTime: metav1.NewTime(now),
						Message:            "The Slice default/workload has been created",
					}).
					Obj(),
			},
			wantSlices: []slice.Slice{*baseSliceWrapper.DeepCopy()},
			wantEvents: []utiltesting.EventRecord{
				{
					Key:       client.ObjectKeyFromObject(baseWorkloadWrapper),
					EventType: corev1.EventTypeNormal,
					Reason:    SliceCreatedEventType,
					Message:   "The Slice default/workload has been created",
				},
			},
		},
		"parse TAS Assignment to populate NodeSelector in Slice": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapperWithAdmission.Clone().Finalizers(SliceControllerName).Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithAdmission.Clone().
					Finalizers(SliceControllerName).
					AdmissionCheck(kueue.AdmissionCheckState{
						Name:               kueue.AdmissionCheckReference(baseAdmissionCheckName),
						State:              kueue.CheckStatePending,
						LastTransitionTime: metav1.NewTime(now),
						Message:            "The Slice default/workload has been created",
					}).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSliceWrapper.DeepCopy(),
			},
			wantEvents: []utiltesting.EventRecord{
				{
					Key:       client.ObjectKeyFromObject(baseWorkloadWrapper),
					EventType: corev1.EventTypeNormal,
					Reason:    SliceCreatedEventType,
					Message:   "The Slice default/workload has been created",
				},
			},
		},
		"error on Slice creation": {
			interceptorFuncsCreate: func(ctx context.Context, client client.WithWatch, obj client.Object, opts ...client.CreateOption) error {
				if _, ok := obj.(*slice.Slice); ok {
					return errTest
				}
				return client.Create(ctx, obj, opts...)
			},
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapperWithAdmission.Finalizers(SliceControllerName).DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithAdmission.Clone().
					Finalizers(SliceControllerName).
					AdmissionCheck(kueue.AdmissionCheckState{
						Name:               kueue.AdmissionCheckReference(baseAdmissionCheckName),
						State:              kueue.CheckStatePending,
						LastTransitionTime: metav1.NewTime(now),
						Message:            "Error creating Slice \"workload\": test error",
					}).
					Obj(),
			},
			wantErr: errTest,
			wantEvents: []utiltesting.EventRecord{
				{
					Key:       client.ObjectKeyFromObject(baseWorkloadWrapper),
					EventType: corev1.EventTypeWarning,
					Reason:    FailedCreateSliceEventType,
					Message:   `Error creating Slice "workload": test error`,
				},
			},
		},
		"should update the Workload AdmissionCheckState when the Slice status is changed to Forming": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapperWithAdmission.Finalizers(SliceControllerName).DeepCopy(),
				baseSliceWrapper.Clone().Forming().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithAdmission.Clone().
					Finalizers(SliceControllerName).
					AdmissionCheck(kueue.AdmissionCheckState{
						Name:               kueue.AdmissionCheckReference(baseAdmissionCheckName),
						State:              kueue.CheckStatePending,
						LastTransitionTime: metav1.NewTime(now),
						Message:            fmt.Sprintf(`The Slice %q is being formed`, baseWorkloadName),
					}).
					Obj(),
			},
			wantSlices: []slice.Slice{*baseSliceWrapper.Clone().Forming().Obj()},
		},
		"should update the Workload AdmissionCheckState when the Slice status is changed to Ready": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapperWithAdmission.Finalizers(SliceControllerName).DeepCopy(),
				baseSliceWrapper.Clone().Ready().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithAdmission.Clone().
					Finalizers(SliceControllerName).
					AdmissionCheck(kueue.AdmissionCheckState{
						Name:               kueue.AdmissionCheckReference(baseAdmissionCheckName),
						State:              kueue.CheckStateReady,
						LastTransitionTime: metav1.NewTime(now),
						Message:            fmt.Sprintf(`The Slice %q is fully operational`, baseWorkloadName),
					}).
					Obj(),
			},
			wantSlices: []slice.Slice{*baseSliceWrapper.Clone().Ready().Obj()},
			wantEvents: []utiltesting.EventRecord{
				{
					Key:       client.ObjectKeyFromObject(baseWorkloadWrapper),
					EventType: corev1.EventTypeNormal,
					Reason:    AdmissionCheckUpdatedEventType,
					Message:   fmt.Sprintf(`Admission check %q updated state from "Pending" to "Ready"`, baseAdmissionCheckName),
				},
			},
		},
		"should update the Workload AdmissionCheckState when the Slice status is changed to Degraded": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapperWithAdmission.Finalizers(SliceControllerName).DeepCopy(),
				baseSliceWrapper.Clone().Degraded().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithAdmission.Clone().
					Finalizers(SliceControllerName).
					AdmissionCheck(kueue.AdmissionCheckState{
						Name:               kueue.AdmissionCheckReference(baseAdmissionCheckName),
						State:              kueue.CheckStateReady,
						LastTransitionTime: metav1.NewTime(now),
						Message:            fmt.Sprintf(`The Slice %q is running with reduced capacity or performance`, baseWorkloadName),
					}).
					Obj(),
			},
			wantSlices: []slice.Slice{*baseSliceWrapper.Clone().Degraded().Obj()},
			wantEvents: []utiltesting.EventRecord{
				{
					Key:       client.ObjectKeyFromObject(baseWorkloadWrapper),
					EventType: corev1.EventTypeNormal,
					Reason:    AdmissionCheckUpdatedEventType,
					Message:   fmt.Sprintf(`Admission check %q updated state from "Pending" to "Ready"`, baseAdmissionCheckName),
				},
			},
		},
		"should update the Workload AdmissionCheckState when the Slice status is changed to Deformed": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapperWithAdmission.Finalizers(SliceControllerName).DeepCopy(),
				baseSliceWrapper.Clone().Deformed().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithAdmission.Clone().
					Finalizers(SliceControllerName).
					AdmissionCheck(kueue.AdmissionCheckState{
						Name:               kueue.AdmissionCheckReference(baseAdmissionCheckName),
						State:              kueue.CheckStateRejected,
						LastTransitionTime: metav1.NewTime(now),
						Message:            fmt.Sprintf(`The Slice %q is being torn down`, baseWorkloadName),
					}).
					Obj(),
			},
			wantSlices: []slice.Slice{*baseSliceWrapper.Clone().Deformed().Obj()},
			wantEvents: []utiltesting.EventRecord{
				{
					Key:       client.ObjectKeyFromObject(baseWorkloadWrapper),
					EventType: corev1.EventTypeNormal,
					Reason:    AdmissionCheckUpdatedEventType,
					Message:   fmt.Sprintf(`Admission check %q updated state from "Pending" to "Rejected"`, baseAdmissionCheckName),
				},
			},
		},
		"should update the Workload AdmissionCheckState when the Slice status is changed to Error": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapperWithAdmission.Finalizers(SliceControllerName).DeepCopy(),
				baseSliceWrapper.Clone().Error().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithAdmission.Clone().
					Finalizers(SliceControllerName).
					AdmissionCheck(kueue.AdmissionCheckState{
						Name:               kueue.AdmissionCheckReference(baseAdmissionCheckName),
						State:              kueue.CheckStateRejected,
						LastTransitionTime: metav1.NewTime(now),
						Message:            fmt.Sprintf(`The Slice %q is not operational due to an error: Error by test`, baseWorkloadName),
					}).
					Obj(),
			},
			wantSlices: []slice.Slice{*baseSliceWrapper.Clone().Error().Obj()},
			wantEvents: []utiltesting.EventRecord{
				{
					Key:       client.ObjectKeyFromObject(baseWorkloadWrapper),
					EventType: corev1.EventTypeNormal,
					Reason:    AdmissionCheckUpdatedEventType,
					Message:   fmt.Sprintf(`Admission check %q updated state from "Pending" to "Rejected"`, baseAdmissionCheckName),
				},
			},
		},
		"should use the first AdmissionCheck if more than one is found": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseAdmissionCheckWrapper.Clone().Name(baseAdmissionCheckName + "2").Obj(),
				baseWorkloadWrapperWithAdmission.Finalizers(SliceControllerName).DeepCopy(),
				baseSliceWrapper.Clone().Ready().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapperWithAdmission.Clone().
					Finalizers(SliceControllerName).
					AdmissionCheck(kueue.AdmissionCheckState{
						Name:               kueue.AdmissionCheckReference(baseAdmissionCheckName),
						State:              kueue.CheckStateReady,
						LastTransitionTime: metav1.NewTime(now),
						Message:            fmt.Sprintf(`The Slice %q is fully operational`, baseWorkloadName),
					}).
					Obj(),
			},
			wantSlices: []slice.Slice{*baseSliceWrapper.Clone().Ready().Obj()},
			wantEvents: []utiltesting.EventRecord{
				{
					Key:       client.ObjectKeyFromObject(baseWorkloadWrapper),
					EventType: corev1.EventTypeNormal,
					Reason:    AdmissionCheckUpdatedEventType,
					Message:   fmt.Sprintf(`Admission check %q updated state from "Pending" to "Ready"`, baseAdmissionCheckName),
				},
			},
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			scheme := runtime.NewScheme()
			utilruntime.Must(kueue.AddToScheme(scheme))
			utilruntime.Must(slice.AddToScheme(scheme))

			interceptorFuncs := interceptor.Funcs{SubResourcePatch: utiltesting.TreatSSAAsStrategicMerge}
			if tc.interceptorFuncsCreate != nil {
				interceptorFuncs.Create = tc.interceptorFuncsCreate
			}

			ctx, _ := utiltesting.ContextWithLog(t)
			clientBuilder := fake.NewClientBuilder().WithScheme(scheme).
				WithStatusSubresource(&kueue.Workload{}).
				WithObjects(tc.objs...).
				WithInterceptorFuncs(interceptorFuncs)

			kClient := clientBuilder.Build()
			recorder := &utiltesting.EventRecorder{}
			reconciler := NewWorkloadReconciler(kClient, recorder)
			reconciler.clock = fakeClock

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

			if diff := cmp.Diff(tc.wantEvents, recorder.RecordedEvents); diff != "" {
				t.Errorf("Unexpected events (-want/+got):\n%s", diff)
			}
		})
	}
}

func TestSliceHandlerHandleEvent(t *testing.T) {
	const (
		baseWlName    = "wl"
		baseSliceName = "slice"
	)

	type requestDuration struct {
		Request  reconcile.Request
		Duration time.Duration
	}

	cases := map[string]struct {
		obj  client.Object
		want []requestDuration
	}{
		"invalid object": {
			obj: utiltesting.MakeWorkload(baseWlName, corev1.NamespaceDefault).Obj(),
		},
		"has a workload that should be handled": {
			obj: utiltesting.MakeSliceWrapper(baseSliceName, corev1.NamespaceDefault).
				ControllerReference(kueue.SchemeGroupVersion.WithKind("Workload"), baseWlName, baseWlName).
				Obj(),
			want: []requestDuration{
				{
					Request: reconcile.Request{
						NamespacedName: types.NamespacedName{
							Namespace: corev1.NamespaceDefault,
							Name:      baseWlName,
						},
					},
					Duration: updatesBatchPeriod,
				},
			},
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			scheme := runtime.NewScheme()
			utilruntime.Must(kueue.AddToScheme(scheme))
			utilruntime.Must(slice.AddToScheme(scheme))
			utilruntime.Must(jobset.AddToScheme(scheme))

			ctx, _ := utiltesting.ContextWithLog(t)
			clientBuilder := fake.NewClientBuilder().WithScheme(scheme)

			kClient := clientBuilder.Build()
			testSliceHandler := &sliceHandler{client: kClient}

			var gotRequestDurations []requestDuration
			testFakePriorityQueue := &fakePriorityQueue{
				addAfter: func(item reconcile.Request, duration time.Duration) {
					gotRequestDurations = append(gotRequestDurations, requestDuration{Request: item, Duration: duration})
				},
			}

			testSliceHandler.handleEvent(ctx, tc.obj, testFakePriorityQueue)
			if diff := cmp.Diff(tc.want, gotRequestDurations); diff != "" {
				t.Errorf("Result after handleEvent (-want,+got):\n%s", diff)
			}
		})
	}
}

type fakePriorityQueue struct {
	workqueue.TypedRateLimitingInterface[reconcile.Request]
	addAfter func(item reconcile.Request, duration time.Duration)
}

func (f *fakePriorityQueue) AddAfter(item reconcile.Request, duration time.Duration) {
	f.addAfter(item, duration)
}

func (f *fakePriorityQueue) Add(reconcile.Request) {}

func (f *fakePriorityQueue) AddWithOpts(priorityqueue.AddOpts, ...reconcile.Request) {}

func (f *fakePriorityQueue) GetWithPriority() (item reconcile.Request, priority int, shutdown bool) {
	panic("GetWithPriority is not expected to be called")
}
