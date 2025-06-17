/*
Copyright 2025.

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
	utiltesting "tpu-slice-controller/internal/util/testing"

	utilruntime "k8s.io/apimachinery/pkg/util/runtime"

	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	"tpu-slice-controller/api/v1alpha1"

	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
)

var (
	baseCmpOpts = cmp.Options{
		cmpopts.EquateEmpty(),
		cmpopts.IgnoreFields(metav1.ObjectMeta{}, "ResourceVersion"),
		cmpopts.IgnoreFields(metav1.Condition{}, "LastTransitionTime"),
	}
)

func TestWorkloadReconciler(t *testing.T) {
	baseWorkloadName := "workload"
	baseRequest := types.NamespacedName{Name: baseWorkloadName, Namespace: v1.NamespaceDefault}
	baseWorkloadWrapper := utiltesting.MakeWorkload(baseWorkloadName, v1.NamespaceDefault)
	baseSliceWrapper := utiltesting.MakeSliceWrapper(baseWorkloadName, v1.NamespaceDefault)

	cases := map[string]struct {
		request       types.NamespacedName
		workload      *kueue.Workload
		slice         *v1alpha1.Slice
		wantWorkloads []kueue.Workload
		wantSlices    []v1alpha1.Slice
		wantErr       error
	}{
		"workload not found": {
			request:       types.NamespacedName{Name: "other-workload", Namespace: v1.NamespaceDefault},
			workload:      baseWorkloadWrapper.DeepCopy(),
			slice:         baseSliceWrapper.DeepCopy(),
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.DeepCopy()},
			wantSlices:    []v1alpha1.Slice{*baseSliceWrapper.DeepCopy()},
		},
		"should delete finalizer because workload has DeletionTimestamp": {
			request: baseRequest,
			workload: baseWorkloadWrapper.Clone().
				DeletionTimestamp(time.Now()).
				Finalizers(CleanupSliceFinalizerName).
				Obj(),
			slice: baseSliceWrapper.DeepCopy(),
		},
		"should delete finalizer because workload is finished": {
			request:       baseRequest,
			workload:      baseWorkloadWrapper.Clone().Finalizers(CleanupSliceFinalizerName).Finished().Obj(),
			slice:         baseSliceWrapper.DeepCopy(),
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().Finished().Obj()},
		},
		"should delete finalizer because workload is evicted": {
			request:       baseRequest,
			workload:      baseWorkloadWrapper.Clone().Finalizers(CleanupSliceFinalizerName).Evicted().Obj(),
			slice:         baseSliceWrapper.DeepCopy(),
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().Evicted().Obj()},
		},
		"should delete finalizer because workload is deactivated": {
			request:       baseRequest,
			workload:      baseWorkloadWrapper.Clone().Finalizers(CleanupSliceFinalizerName).Active(false).Obj(),
			slice:         baseSliceWrapper.DeepCopy(),
			wantWorkloads: []kueue.Workload{*baseWorkloadWrapper.Clone().Active(false).Obj()},
		},
		"should add finalizer and create slice": {
			request:  baseRequest,
			workload: baseWorkloadWrapper.UID(types.UID(baseWorkloadName)).DeepCopy(),
			wantWorkloads: []kueue.Workload{
				*baseWorkloadWrapper.Clone().
					UID(types.UID(baseWorkloadName)).
					Finalizers(CleanupSliceFinalizerName).
					Obj(),
			},
			wantSlices: []v1alpha1.Slice{
				*baseSliceWrapper.Clone().
					ControllerReference(kueue.GroupVersion.WithKind("Workload"), baseWorkloadName, baseWorkloadName).
					Obj(),
			},
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			scheme := runtime.NewScheme()
			utilruntime.Must(kueue.AddToScheme(scheme))
			utilruntime.Must(v1alpha1.AddToScheme(scheme))

			ctx, _ := utiltesting.ContextWithLog(t)
			clientBuilder := fake.NewClientBuilder().WithScheme(scheme)

			if tc.workload != nil {
				clientBuilder.WithObjects(tc.workload)
			}
			if tc.slice != nil {
				clientBuilder.WithObjects(tc.slice)
			}

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

			slices := &v1alpha1.SliceList{}
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
