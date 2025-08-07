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
	batchv1 "k8s.io/api/batch/v1"
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
	utiltestingjobsjobset "tpu-slice-controller/internal/util/testingjobs/jobset"
	utiltestingjobspod "tpu-slice-controller/internal/util/testingjobs/pod"
)

var (
	baseCmpOpts = cmp.Options{
		cmpopts.EquateEmpty(),
		cmpopts.IgnoreFields(metav1.ObjectMeta{}, "ResourceVersion"),
		cmpopts.IgnoreFields(metav1.Condition{}, "LastTransitionTime"),
		cmpopts.EquateApproxTime(time.Second),
	}
	errTest = errors.New("test error")
)

var (
	jobSetGVK   = jobset.SchemeGroupVersion.WithKind("JobSet")
	jobGVK      = batchv1.SchemeGroupVersion.WithKind("Job")
	workloadGVK = kueue.SchemeGroupVersion.WithKind("Workload")
)

func TestWorkloadReconciler(t *testing.T) {
	const (
		baseACName       = "ac"
		baseJobName      = "job"
		baseJobSetName   = "jobset"
		basePod1Name     = "pod1"
		basePod2Name     = "pod2"
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

	buildEventRecord := func(eventType, reason, message string) utiltesting.EventRecord {
		return utiltesting.EventRecord{
			Key:       client.ObjectKey{Namespace: corev1.NamespaceDefault, Name: baseWorkloadName},
			EventType: eventType,
			Reason:    reason,
			Message:   message,
		}
	}

	baseRequest := types.NamespacedName{Name: baseWorkloadName, Namespace: corev1.NamespaceDefault}
	baseJobSetWrapper := utiltestingjobsjobset.MakeJobSet(baseJobSetName, corev1.NamespaceDefault)
	basePod1Wrapper := utiltestingjobspod.MakePod(basePod1Name, corev1.NamespaceDefault).
		OwnerReference(baseJobSetName, jobSetGVK).
		Label(jobset.JobSetNameKey, baseJobSetName)
	basePod2Wrapper := basePod1Wrapper.Clone().Name(basePod2Name)
	baseAdmissionCheckWrapper := utiltesting.MakeAdmissionCheck(baseACName).ControllerName(SliceControllerName)
	basePodSet1Wrapper := *utiltesting.MakePodSet("ps1", 2).
		Annotation(core.TPUTopologyAnnotation, "4x4x12").
		NodeSelector(core.TPUAcceleratorLabel, "tpu-v7x")
	basePodSet2Wrapper := basePodSet1Wrapper.Clone().Name("ps2")
	basePodSets := []kueue.PodSet{
		*basePodSet1Wrapper.DeepCopy(),
		*basePodSet2Wrapper.DeepCopy(),
	}
	baseLevels := []string{core.TPUBlockLabel, core.TPUSubBlockLabel}
	basePodSetAssignment1Wrapper := utiltesting.MakePodSetAssignment("ps1").
		TopologyAssignment(baseLevels, []kueue.TopologyDomainAssignment{
			{
				Values: []string{"block1", "subblock1"},
				Count:  2,
			},
		})
	basePodSetAssignment2Wrapper := utiltesting.MakePodSetAssignment("ps2").
		TopologyAssignment(baseLevels, []kueue.TopologyDomainAssignment{
			{
				Values: []string{"block1", "subblock2"},
				Count:  2,
			},
		})
	baseAdmission := &kueue.Admission{
		PodSetAssignments: []kueue.PodSetAssignment{
			basePodSetAssignment1Wrapper.Obj(),
			basePodSetAssignment2Wrapper.Obj(),
		},
	}
	baseWorkloadWrapper := utiltesting.MakeWorkload(baseWorkloadName, corev1.NamespaceDefault).
		UID(baseWorkloadName).
		AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, ""))
	baseSlice1Wrapper := utiltesting.MakeSliceWrapper(core.SliceName(baseWorkloadName, "ps1"), corev1.NamespaceDefault).
		ControllerReference(workloadGVK, baseWorkloadName, baseWorkloadName).
		NodeSelector(map[string][]string{"cloud.google.com/gke-tpu-slice-4x4x4-id": {"subblock1"}})
	baseSlice2Wrapper := baseSlice1Wrapper.Clone().Name(core.SliceName(baseWorkloadName, "ps2")).
		NodeSelector(map[string][]string{"cloud.google.com/gke-tpu-slice-4x4x4-id": {"subblock2"}})

	testCases := map[string]struct {
		interceptorFuncsCreate func(ctx context.Context, client client.WithWatch, obj client.Object, opts ...client.CreateOption) error
		request                types.NamespacedName
		objs                   []client.Object
		wantWorkloads          []kueue.Workload
		wantSlices             []slice.Slice
		wantErr                error
		wantEvents             []utiltesting.EventRecord
	}{
		"should skip reconciliation because the Workload was not found": {
			request:       types.NamespacedName{Name: "other-workload", Namespace: corev1.NamespaceDefault},
			objs:          []client.Object{baseWorkloadWrapper.Clone().Finalizers(SliceControllerName).Obj()},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().Finalizers(SliceControllerName).Obj()},
		},
		"should skip reconciliation because the Workload already finalized": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers("test").
					DeletionTimestamp(now).
					Obj(),
				baseSlice1Wrapper.Clone().DeletionTimestamp(now).Finalizers("test").Obj(),
				baseSlice2Wrapper.Clone().DeletionTimestamp(now).Finalizers("test").Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers("test").
					DeletionTimestamp(now).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().DeletionTimestamp(now).Finalizers("test").Obj(),
				*baseSlice2Wrapper.Clone().DeletionTimestamp(now).Finalizers("test").Obj(),
			},
		},
		"should delete the finalizer because the Workload has a DeletionTimestamp": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					DeletionTimestamp(now).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
		},
		"should delete the finalizer because the Workload is finished": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finished().
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().
				PodSets(basePodSets...).
				ReserveQuota(baseAdmission, now).
				ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).Finished().Obj()},
		},
		"should delete the finalizer because the Workload is evicted": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Evicted().
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().
				PodSets(basePodSets...).
				ReserveQuota(baseAdmission, now).
				ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).Evicted().Obj()},
		},
		"should delete the finalizer because the Workload is deactivated": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().
				PodSets(basePodSets...).
				ReserveQuota(baseAdmission, now).
				ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).Active(false).Obj()},
		},
		"should delete the finalizer because the Workload has no owner": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).Finalizers(SliceControllerName).Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					Obj(),
			},
		},
		"should delete the finalizer because the Workload has an unsupported owner": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobGVK, baseJobName, baseJobName).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobGVK, baseJobName, baseJobName).
					Obj(),
			},
		},
		"should delete the finalizer because Slices with status Deformed": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseJobSetWrapper.DeepCopy(),
				basePod1Wrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.Clone().Deformed().Obj(),
				baseSlice2Wrapper.Clone().Deformed().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).Active(false).Obj(),
			},
		},
		"shouldn't delete the finalizer because Slices status Degraded": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseJobSetWrapper.DeepCopy(),
				basePod1Wrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.Clone().Degraded().Obj(),
				baseSlice2Wrapper.Clone().Degraded().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Finalizers(SliceControllerName).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().Degraded().Obj(),
				*baseSlice2Wrapper.Clone().Degraded().Obj(),
			},
		},
		"should delete the finalizer because the Pod Status Succeeded": {
			request: baseRequest,
			objs: []client.Object{
				baseJobSetWrapper.DeepCopy(),
				basePod1Wrapper.Clone().StatusPhase(corev1.PodSucceeded).Obj(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Obj(),
			},
		},
		"should delete the finalizer because the Pod Status PodFailed": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseJobSetWrapper.DeepCopy(),
				basePod1Wrapper.Clone().StatusPhase(corev1.PodFailed).Obj(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Obj(),
			},
		},
		"shouldn't delete the finalizer because Pods still running": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseJobSetWrapper.DeepCopy(),
				basePod1Wrapper.DeepCopy(),
				basePod2Wrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Finalizers(SliceControllerName).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.DeepCopy(),
				*baseSlice2Wrapper.DeepCopy(),
			},
		},
		"shouldn't delete the finalizer because one of the Pods still running": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseJobSetWrapper.DeepCopy(),
				basePod1Wrapper.Clone().StatusPhase(corev1.PodSucceeded).Obj(),
				basePod2Wrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Active(false).
					Finalizers(SliceControllerName).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.DeepCopy(),
				*baseSlice2Wrapper.DeepCopy(),
			},
		},
		"shouldn't add finalizer because invalid TPU topology annotation": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
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
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
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
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
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
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
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
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Obj(),
			},
		},
		"shouldn't add finalizer because there’s no TopologyAssignment": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					ReserveQuota(
						&kueue.Admission{
							PodSetAssignments: []kueue.PodSetAssignment{
								utiltesting.MakePodSetAssignment("ps1").Obj(),
							},
						}, now,
					).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					ReserveQuota(
						&kueue.Admission{
							PodSetAssignments: []kueue.PodSetAssignment{
								utiltesting.MakePodSetAssignment("ps1").Obj(),
							},
						}, now,
					).
					Obj(),
			},
		},
		"should add finalizer": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
			},
		},
		"shouldn't create a Slice because there’s no AdmissionCheck": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
			},
		},
		"should create Slices": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, `Slices are in states: 2 Created`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.DeepCopy(),
				*baseSlice2Wrapper.DeepCopy(),
			},
			wantEvents: []utiltesting.EventRecord{
				buildEventRecord(corev1.EventTypeNormal, SlicesCreatedEventType,
					`The Slices "default/workload-ps1", "default/workload-ps2" have been created`),
			},
		},
		"should create Slices only for relevant PodSets (invalid pod template)": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					PodSets(
						*utiltesting.MakePodSet("ps1", 2).
							Annotation(core.TPUTopologyAnnotation, "4x4x12").
							NodeSelector(core.TPUAcceleratorLabel, "tpu-v7x").
							Obj(),
						*utiltesting.MakePodSet("ps2", 2).
							Annotation(core.TPUTopologyAnnotation, "4x4x12").
							NodeSelector(core.TPUAcceleratorLabel, "tpu-v8x").
							Obj(),
					).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					PodSets(
						*utiltesting.MakePodSet("ps1", 2).
							Annotation(core.TPUTopologyAnnotation, "4x4x12").
							NodeSelector(core.TPUAcceleratorLabel, "tpu-v7x").
							Obj(),
						*utiltesting.MakePodSet("ps2", 2).
							Annotation(core.TPUTopologyAnnotation, "4x4x12").
							NodeSelector(core.TPUAcceleratorLabel, "tpu-v8x").
							Obj(),
					).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, `Slices are in states: 1 Created`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.DeepCopy(),
			},
			wantEvents: []utiltesting.EventRecord{
				buildEventRecord(corev1.EventTypeNormal, SlicesCreatedEventType,
					`The Slices "default/workload-ps1" have been created`),
			},
		},
		"should create Slices only for relevant PodSets (invalid assignment)": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					ReserveQuota(
						&kueue.Admission{
							PodSetAssignments: []kueue.PodSetAssignment{
								*basePodSetAssignment1Wrapper.DeepCopy(),
								utiltesting.MakePodSetAssignment("ps2").Obj(),
							},
						}, now,
					).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					ReserveQuota(
						&kueue.Admission{
							PodSetAssignments: []kueue.PodSetAssignment{
								*basePodSetAssignment1Wrapper.DeepCopy(),
								utiltesting.MakePodSetAssignment("ps2").Obj(),
							},
						}, now,
					).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, `Slices are in states: 1 Created`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.DeepCopy(),
			},
			wantEvents: []utiltesting.EventRecord{
				buildEventRecord(corev1.EventTypeNormal, SlicesCreatedEventType,
					`The Slices "default/workload-ps1" have been created`),
			},
		},
		"should create missed Slices": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, `Slices are in states: 2 Created`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.DeepCopy(),
				*baseSlice2Wrapper.DeepCopy(),
			},
			wantEvents: []utiltesting.EventRecord{
				buildEventRecord(corev1.EventTypeNormal, SlicesCreatedEventType,
					`The Slices "default/workload-ps2" have been created`),
			},
		},
		"parse TAS Assignment to populate NodeSelector in Slice": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, `Slices are in states: 2 Created`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.DeepCopy(),
				*baseSlice2Wrapper.DeepCopy(),
			},
			wantEvents: []utiltesting.EventRecord{
				buildEventRecord(corev1.EventTypeNormal, SlicesCreatedEventType,
					`The Slices "default/workload-ps1", "default/workload-ps2" have been created`),
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
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, `Error creating Slice "default/workload-ps1": test error`)).
					Obj(),
			},
			wantErr: errTest,
			wantEvents: []utiltesting.EventRecord{
				buildEventRecord(corev1.EventTypeWarning, FailedCreateSliceEventType,
					`Error creating Slice "default/workload-ps1": test error`),
			},
		},
		"should update the Workload's AdmissionCheckState": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.DeepCopy(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, `Slices are in states: 2 Created`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.DeepCopy(),
				*baseSlice2Wrapper.DeepCopy(),
			},
		},
		"should update the Workload's AdmissionCheckState when one Slice is in the Forming state": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.Clone().Forming().Obj(),
				baseSlice2Wrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, `Slices are in states: 1 Created, 1 Forming`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().Forming().Obj(),
				*baseSlice2Wrapper.DeepCopy(),
			},
		},
		"should update the Workload's AdmissionCheckState when all Slices are in the Forming state": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.Clone().Forming().Obj(),
				baseSlice2Wrapper.Clone().Forming().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, `Slices are in states: 2 Forming`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().Forming().Obj(),
				*baseSlice2Wrapper.Clone().Forming().Obj(),
			},
		},
		"should update the Workload's AdmissionCheckState when one Slice is in the Ready state": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.Clone().Ready().Obj(),
				baseSlice2Wrapper.Clone().Forming().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStatePending, `Slices are in states: 1 Forming, 1 Ready`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().Ready().Obj(),
				*baseSlice2Wrapper.Clone().Forming().Obj(),
			},
		},
		"should update the Workload's AdmissionCheckState when all Slices are in the Ready state": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.Clone().Ready().Obj(),
				baseSlice2Wrapper.Clone().Ready().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStateReady, `Slices are in states: 2 Ready`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().Ready().Obj(),
				*baseSlice2Wrapper.Clone().Ready().Obj(),
			},
			wantEvents: []utiltesting.EventRecord{
				buildEventRecord(corev1.EventTypeNormal, AdmissionCheckUpdatedEventType,
					fmt.Sprintf(`Admission check %q updated state from "Pending" to "Ready"`, baseACName)),
			},
		},
		"should update the Workload's AdmissionCheckState when one Slice is in the Ready state and another is in the Degraded state": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.Clone().Ready().Obj(),
				baseSlice2Wrapper.Clone().Degraded().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStateReady, `Slices are in states: 1 Degraded, 1 Ready`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().Ready().Obj(),
				*baseSlice2Wrapper.Clone().Degraded().Obj()},
			wantEvents: []utiltesting.EventRecord{
				buildEventRecord(corev1.EventTypeNormal, AdmissionCheckUpdatedEventType,
					fmt.Sprintf(`Admission check %q updated state from "Pending" to "Ready"`, baseACName)),
			},
		},
		"should update the Workload's AdmissionCheckState when one Slice is in the Error state": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.Clone().Ready().Obj(),
				baseSlice2Wrapper.Clone().Error().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStateRejected, `Slices are in states: 1 Error, 1 Ready. Errors: Error by test`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().Ready().Obj(),
				*baseSlice2Wrapper.Clone().Error().Obj()},
			wantEvents: []utiltesting.EventRecord{
				buildEventRecord(corev1.EventTypeNormal, AdmissionCheckUpdatedEventType,
					fmt.Sprintf(`Admission check %q updated state from "Pending" to "Rejected"`, baseACName)),
			},
		},
		"should update the Workload's AdmissionCheckState when one Slice is in the Deformed state": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.Clone().Ready().Obj(),
				baseSlice2Wrapper.Clone().Deformed().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStateRejected, `Slices are in states: 1 Deformed, 1 Ready`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().Ready().Obj(),
				*baseSlice2Wrapper.Clone().Deformed().Obj()},
			wantEvents: []utiltesting.EventRecord{
				buildEventRecord(corev1.EventTypeNormal, AdmissionCheckUpdatedEventType,
					fmt.Sprintf(`Admission check %q updated state from "Pending" to "Rejected"`, baseACName)),
			},
		},
		"should use the first AdmissionCheck if more than one is found": {
			request: baseRequest,
			objs: []client.Object{
				baseAdmissionCheckWrapper.DeepCopy(),
				baseAdmissionCheckWrapper.Clone().Name(baseACName + "2").Obj(),
				baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					Obj(),
				baseSlice1Wrapper.Clone().Ready().Obj(),
				baseSlice2Wrapper.Clone().Ready().Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					PodSets(basePodSets...).
					ReserveQuota(baseAdmission, now).
					ControllerReference(jobSetGVK, baseJobSetName, baseJobSetName).
					Finalizers(SliceControllerName).
					AdmissionCheck(buildAdmissionCheckState(kueue.CheckStateReady, `Slices are in states: 2 Ready`)).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSlice1Wrapper.Clone().Ready().Obj(),
				*baseSlice2Wrapper.Clone().Ready().Obj(),
			},
			wantEvents: []utiltesting.EventRecord{
				buildEventRecord(corev1.EventTypeNormal, AdmissionCheckUpdatedEventType,
					fmt.Sprintf(`Admission check %q updated state from "Pending" to "Ready"`, baseACName)),
			},
		},
	}
	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			scheme := runtime.NewScheme()
			utilruntime.Must(corev1.AddToScheme(scheme))
			utilruntime.Must(jobset.AddToScheme(scheme))
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

			indexer := utiltesting.AsIndexer(clientBuilder)
			if err := SetupIndexer(ctx, indexer); err != nil {
				t.Fatalf("Setup failed: %v", err)
			}

			kClient := clientBuilder.Build()
			recorder := &utiltesting.EventRecorder{}
			reconciler := NewWorkloadReconciler(kClient, recorder)
			reconciler.clock = testingclock.NewFakeClock(now)

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
				ControllerReference(workloadGVK, baseWlName, baseWlName).
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

			indexer := utiltesting.AsIndexer(clientBuilder)
			if err := SetupIndexer(ctx, indexer); err != nil {
				t.Fatalf("Setup failed: %v", err)
			}

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
