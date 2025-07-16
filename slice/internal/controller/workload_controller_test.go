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
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	"k8s.io/client-go/util/workqueue"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/controller/priorityqueue"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueuealpha "sigs.k8s.io/kueue/apis/kueue/v1alpha1"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	slice "tpu-slice-controller/api/v1alpha1"
	utiltesting "tpu-slice-controller/internal/util/testing"
	utiltestingjobsjobset "tpu-slice-controller/internal/util/testingjobs/jobset"
	utiltestingjobspod "tpu-slice-controller/internal/util/testingjobs/pod"
)

var (
	baseCmpOpts = cmp.Options{
		cmpopts.EquateEmpty(),
		cmpopts.IgnoreFields(metav1.ObjectMeta{}, "ResourceVersion"),
		cmpopts.IgnoreFields(metav1.Condition{}, "LastTransitionTime"),
	}
)

func TestWorkloadReconcilerReconcile(t *testing.T) {
	const (
		baseJobSetName   = "jobset"
		basePodName      = "pod"
		baseWorkloadName = "workload"
	)

	baseRequest := types.NamespacedName{Name: baseWorkloadName, Namespace: corev1.NamespaceDefault}
	baseJobSetWrapper := utiltestingjobsjobset.MakeJobSet(baseJobSetName, corev1.NamespaceDefault)
	basePodWrapper := utiltestingjobspod.MakePod(basePodName, corev1.NamespaceDefault)
	baseWorkloadWrapper := utiltesting.MakeWorkload(baseWorkloadName, corev1.NamespaceDefault)
	baseSliceWrapper := utiltesting.MakeSliceWrapper(baseWorkloadName, corev1.NamespaceDefault)

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
				baseWorkloadWrapper.Clone().Finalizers(CleanupSliceFinalizerName).Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().Finalizers(CleanupSliceFinalizerName).Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSliceWrapper.DeepCopy(),
			},
		},
		"should delete the Slice because the Workload has no owner": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().Finalizers(CleanupSliceFinalizerName).Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().Finalizers(CleanupSliceFinalizerName).Obj(),
			},
		},
		"should delete the Slice because the Workload has an unsupported owner": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(batchv1.SchemeGroupVersion.WithKind("Job"), "job", "job").
					Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(batchv1.SchemeGroupVersion.WithKind("Job"), "job", "job").
					Obj(),
			},
		},
		"shouldn't delete the Slice because the Workload has an supported owner": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSliceWrapper.DeepCopy(),
			},
		},
		"should delete the Slice because the Workload has a DeletionTimestamp and the JobSet is not found": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					DeletionTimestamp(time.Now()).
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					DeletionTimestamp(time.Now()).
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
			},
		},
		"should delete the Slice because the Workload is finished and the JobSet is not found": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Finished().
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().
				Finished().
				Finalizers(CleanupSliceFinalizerName).
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
				Obj(),
			},
		},
		"should delete the Slice because the Workload is evicted and the JobSet is not found": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Evicted().
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().
				Evicted().
				Finalizers(CleanupSliceFinalizerName).
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
				Obj(),
			},
		},
		"should delete the Slice because the Workload is deactivated and the JobSet is not found": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Active(false).
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().
				Active(false).
				Finalizers(CleanupSliceFinalizerName).
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
				Obj(),
			},
		},
		"should delete the Slice because the Workload is deactivated and Pods are not found": {
			request: baseRequest,
			objs: []client.Object{
				baseJobSetWrapper.Clone().Obj(),
				baseWorkloadWrapper.Clone().
					Active(false).
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().
				Active(false).
				Finalizers(CleanupSliceFinalizerName).
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
				Obj(),
			},
		},
		"shouldn't delete the Slice because the Workload is deactivated but Pods still running": {
			request: baseRequest,
			objs: []client.Object{
				baseJobSetWrapper.Clone().Obj(),
				basePodWrapper.Clone().
					OwnerReference(baseJobSetName, jobset.SchemeGroupVersion.WithKind("JobSet")).
					Label(jobset.JobSetNameKey, baseJobSetName).
					Obj(),
				baseWorkloadWrapper.Clone().
					Active(false).
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().
				Active(false).
				Finalizers(CleanupSliceFinalizerName).
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
				Obj(),
			},
			wantSlices: []slice.Slice{*baseSliceWrapper.DeepCopy()},
		},
		"should delete the finalizer because the Workload is evicted and the Slice not found": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Evicted().
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().
				Evicted().
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
				Obj(),
			},
		},
		"should delete the finalizer because the Workload is evicted and the Slice in deformed state": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Evicted().
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
				baseSliceWrapper.Clone().
					Deformed().
					Finalizers(CleanupSliceFinalizerName).
					DeletionTimestamp(time.Now()).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().
				Evicted().
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
				Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSliceWrapper.Clone().
					Deformed().
					Finalizers(CleanupSliceFinalizerName).
					DeletionTimestamp(time.Now()).
					Obj(),
			},
		},
		"should add finalizer and create a Slice": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					UID(baseWorkloadName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					UID(baseWorkloadName).
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSliceWrapper.Clone().
					ControllerReference(kueue.GroupVersion.WithKind("Workload"), baseWorkloadName, baseWorkloadName).
					Obj(),
			},
		},
		"should create a Slice (finalizer already exists)": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					UID(baseWorkloadName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					UID(baseWorkloadName).
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSliceWrapper.Clone().
					ControllerReference(kueue.GroupVersion.WithKind("Workload"), baseWorkloadName, baseWorkloadName).
					Obj(),
			},
		},
		"shouldn't create the Slice because it has already been created": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					Finalizers(CleanupSliceFinalizerName).
					UID(baseWorkloadName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
				baseSliceWrapper.DeepCopy(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					UID(baseWorkloadName).
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			wantSlices: []slice.Slice{*baseSliceWrapper.Clone().Obj()},
		},
		"should parse TAS Assignment to populate NodeSelector in Slice": {
			request: baseRequest,
			objs: []client.Object{
				baseWorkloadWrapper.Clone().
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					UID(baseWorkloadName).
					PodSetAssignments(utiltesting.MakePodSetAssignment("psa1").
						TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
							{
								Values: []string{"domain1", "domain2"},
								Count:  2,
							},
						}).Obj(),
						utiltesting.MakePodSetAssignment("psa2").
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{
									Values: []string{"domain2", "domain3"},
									Count:  2,
								},
							}).
							Obj(),
					).Obj(),
			},
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), baseJobSetName, baseJobSetName).
					UID(types.UID(baseWorkloadName)).
					PodSetAssignments(utiltesting.MakePodSetAssignment("psa1").
						TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
							{
								Values: []string{"domain1", "domain2"},
								Count:  2,
							},
						}).Obj(),
						utiltesting.MakePodSetAssignment("psa2").
							TopologyAssignment(nil, []kueue.TopologyDomainAssignment{
								{
									Values: []string{"domain2", "domain3"},
									Count:  2,
								},
							}).
							Obj(),
					).
					Finalizers(CleanupSliceFinalizerName).
					Obj(),
			},
			wantSlices: []slice.Slice{
				*baseSliceWrapper.Clone().
					ControllerReference(kueue.GroupVersion.WithKind("Workload"), baseWorkloadName, baseWorkloadName).
					NodeSelector(map[string][]string{
						TPUReservationSubblockLabel: {"domain1", "domain2", "domain3"},
					}).
					Obj(),
			},
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			scheme := runtime.NewScheme()
			utilruntime.Must(kueue.AddToScheme(scheme))
			utilruntime.Must(slice.AddToScheme(scheme))
			utilruntime.Must(corev1.AddToScheme(scheme))
			utilruntime.Must(jobset.AddToScheme(scheme))

			ctx, _ := utiltesting.ContextWithLog(t)
			clientBuilder := fake.NewClientBuilder().WithScheme(scheme).WithObjects(tc.objs...)

			kClient := clientBuilder.Build()
			reconciler := NewWorkloadReconciler(kClient)

			_, err := reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: tc.request})
			if diff := cmp.Diff(tc.wantErr, err); diff != "" {
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

func TestWorkloadReconcilerHandleEvent(t *testing.T) {
	cases := map[string]struct {
		obj  client.Object
		want bool
	}{
		"invalid object": {
			obj:  utiltestingjobspod.MakePod("pod", corev1.NamespaceDefault).Obj(),
			want: true,
		},
		"has cleanup slice finalizer": {
			obj: utiltesting.MakeWorkload("wl", corev1.NamespaceDefault).
				Finalizers(CleanupSliceFinalizerName).
				Obj(),
			want: true,
		},
		"has supported owner reference": {
			obj: utiltesting.MakeWorkload("wl", corev1.NamespaceDefault).
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), "jobset", "jobset").
				Obj(),
			want: true,
		},
		"doesn't have owner reference": {
			obj:  utiltesting.MakeWorkload("wl", corev1.NamespaceDefault).Obj(),
			want: false,
		},
		"has unsupported owner reference": {
			obj: utiltesting.MakeWorkload("wl", corev1.NamespaceDefault).
				ControllerReference(batchv1.SchemeGroupVersion.WithKind("Job"), "job", "job").
				Obj(),
			want: false,
		},
		"has DeletionTimestamp": {
			obj: utiltesting.MakeWorkload("wl", corev1.NamespaceDefault).
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), "jobset", "jobset").
				DeletionTimestamp(time.Now()).
				Obj(),
			want: false,
		},
		"finished": {
			obj: utiltesting.MakeWorkload("wl", corev1.NamespaceDefault).
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), "jobset", "jobset").
				Finished().
				Obj(),
			want: false,
		},
		"evicted": {
			obj: utiltesting.MakeWorkload("wl", corev1.NamespaceDefault).
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), "jobset", "jobset").
				Evicted().
				Obj(),
			want: false,
		},
		"deactivated": {
			obj: utiltesting.MakeWorkload("wl", corev1.NamespaceDefault).
				ControllerReference(jobset.SchemeGroupVersion.WithKind("JobSet"), "jobset", "jobset").
				Active(false).
				Obj(),
			want: false,
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			got := NewWorkloadReconciler(nil).handleEvent(tc.obj)
			if diff := cmp.Diff(tc.want, got); diff != "" {
				t.Errorf("Result after Update (-want,+got):\n%s", diff)
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

			indexer := utiltesting.AsIndexer(clientBuilder)
			if err := SetupWorkloadIndexer(ctx, indexer); err != nil {
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

func TestJobSetHandlerHandleEvent(t *testing.T) {
	const (
		baseWlName     = "wl"
		baseJobSetName = "jobset"
	)

	baseJobSetWrapper := utiltestingjobsjobset.MakeJobSet(baseJobSetName, corev1.NamespaceDefault).UID(baseJobSetName)

	type requestDuration struct {
		Request  reconcile.Request
		Duration time.Duration
	}

	cases := map[string]struct {
		objs []client.Object
		obj  client.Object
		want []requestDuration
	}{
		"invalid object": {
			obj: utiltesting.MakeWorkload(baseWlName, corev1.NamespaceDefault).Obj(),
		},
		"doesn't have workload": {
			obj: baseJobSetWrapper.DeepCopy(),
		},
		"has a workload that should not be handled": {
			objs: []client.Object{
				baseJobSetWrapper.DeepCopy(),
				utiltesting.MakeWorkload(baseWlName, corev1.NamespaceDefault).
					ControllerReference(kueue.GroupVersion.WithKind("Workload"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			obj: baseJobSetWrapper.DeepCopy(),
		},
		"has a workload that should be handled": {
			objs: []client.Object{
				utiltesting.MakeWorkload(baseWlName, corev1.NamespaceDefault).
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(kueue.GroupVersion.WithKind("Workload"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			obj: baseJobSetWrapper.DeepCopy(),
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
			clientBuilder := fake.NewClientBuilder().WithScheme(scheme).WithObjects(tc.objs...)

			indexer := utiltesting.AsIndexer(clientBuilder)
			if err := SetupWorkloadIndexer(ctx, indexer); err != nil {
				t.Fatalf("Setup failed: %v", err)
			}

			kClient := clientBuilder.Build()
			testJobSetHandler := &jobSetHandler{client: kClient}

			var gotRequestDurations []requestDuration
			testFakePriorityQueue := &fakePriorityQueue{
				addAfter: func(item reconcile.Request, duration time.Duration) {
					gotRequestDurations = append(gotRequestDurations, requestDuration{Request: item, Duration: duration})
				},
			}

			testJobSetHandler.handleEvent(ctx, tc.obj, testFakePriorityQueue)
			if diff := cmp.Diff(tc.want, gotRequestDurations); diff != "" {
				t.Errorf("Result after handleEvent (-want,+got):\n%s", diff)
			}
		})
	}
}

func TestPodHandlerHandleEvent(t *testing.T) {
	const (
		baseWlName     = "wl"
		baseJobSetName = "jobset"
		basePodName    = "pod"
	)

	baseJobSetWrapper := utiltestingjobsjobset.MakeJobSet(baseJobSetName, corev1.NamespaceDefault).UID(baseJobSetName)

	type requestDuration struct {
		Request  reconcile.Request
		Duration time.Duration
	}

	cases := map[string]struct {
		objs []client.Object
		obj  client.Object
		want []requestDuration
	}{
		"invalid object": {
			obj: utiltesting.MakeWorkload(baseWlName, corev1.NamespaceDefault).Obj(),
		},
		"doesn't have TAS label": {
			obj: utiltestingjobspod.MakePod(basePodName, corev1.NamespaceDefault).Obj(),
		},
		"doesn't have JobSet name label": {
			obj: utiltestingjobspod.MakePod(basePodName, corev1.NamespaceDefault).
				Label(kueuealpha.TASLabel, tasLabelValue).
				Obj(),
		},
		"doesn't have JobSet": {
			objs: []client.Object{
				utiltesting.MakeWorkload(baseWlName, corev1.NamespaceDefault).
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(kueue.GroupVersion.WithKind("Workload"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			obj: utiltestingjobspod.MakePod(basePodName, corev1.NamespaceDefault).
				Label(kueuealpha.TASLabel, tasLabelValue).
				Label(jobset.JobSetNameKey, baseJobSetName).
				Obj(),
		},
		"doesn't have workload": {
			objs: []client.Object{baseJobSetWrapper.DeepCopy()},
			obj: utiltestingjobspod.MakePod(basePodName, corev1.NamespaceDefault).
				Label(kueuealpha.TASLabel, tasLabelValue).
				Label(jobset.JobSetNameKey, baseJobSetName).
				Obj(),
		},
		"has a workload that should not be handled": {
			objs: []client.Object{
				baseJobSetWrapper.DeepCopy(),
				utiltesting.MakeWorkload(baseWlName, corev1.NamespaceDefault).
					ControllerReference(kueue.GroupVersion.WithKind("Workload"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			obj: utiltestingjobspod.MakePod(basePodName, corev1.NamespaceDefault).
				Label(kueuealpha.TASLabel, tasLabelValue).
				Label(jobset.JobSetNameKey, baseJobSetName).
				Obj(),
		},
		"has a workload that should be handled": {
			objs: []client.Object{
				baseJobSetWrapper.DeepCopy(),
				utiltesting.MakeWorkload(baseWlName, corev1.NamespaceDefault).
					Finalizers(CleanupSliceFinalizerName).
					ControllerReference(kueue.GroupVersion.WithKind("Workload"), baseJobSetName, baseJobSetName).
					Obj(),
			},
			obj: utiltestingjobspod.MakePod(basePodName, corev1.NamespaceDefault).
				Label(kueuealpha.TASLabel, tasLabelValue).
				Label(jobset.JobSetNameKey, baseJobSetName).
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
			utilruntime.Must(corev1.AddToScheme(scheme))
			utilruntime.Must(jobset.AddToScheme(scheme))

			ctx, _ := utiltesting.ContextWithLog(t)
			clientBuilder := fake.NewClientBuilder().WithScheme(scheme).WithObjects(tc.objs...)

			indexer := utiltesting.AsIndexer(clientBuilder)
			if err := SetupWorkloadIndexer(ctx, indexer); err != nil {
				t.Fatalf("Setup failed: %v", err)
			}

			kClient := clientBuilder.Build()
			testPodHandler := &podHandler{client: kClient}

			var gotRequestDurations []requestDuration
			testFakePriorityQueue := &fakePriorityQueue{
				addAfter: func(item reconcile.Request, duration time.Duration) {
					gotRequestDurations = append(gotRequestDurations, requestDuration{Request: item, Duration: duration})
				},
			}

			testPodHandler.handleEvent(ctx, tc.obj, testFakePriorityQueue)
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
