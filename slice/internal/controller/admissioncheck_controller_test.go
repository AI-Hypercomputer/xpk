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

	"github.com/google/go-cmp/cmp"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	utiltesting "tpu-slice-controller/internal/util/testing"
)

func TestAdmissionCheckReconciler(t *testing.T) {
	baseAdmissionCheckName := "ac"
	baseGeneration := int64(1)
	baseRequest := types.NamespacedName{Name: baseAdmissionCheckName, Namespace: corev1.NamespaceDefault}
	baseAdmissionCheckWrapper := utiltesting.MakeAdmissionCheck(baseAdmissionCheckName).
		Generation(baseGeneration).
		ControllerName(SliceControllerName)

	testCases := map[string]struct {
		request             types.NamespacedName
		admissionCheck      *kueue.AdmissionCheck
		wantAdmissionChecks []kueue.AdmissionCheck
		wantErr             error
	}{
		"unrelated check": {
			request:        baseRequest,
			admissionCheck: baseAdmissionCheckWrapper.Clone().ControllerName("other-controller").Obj(),
			wantAdmissionChecks: []kueue.AdmissionCheck{
				*baseAdmissionCheckWrapper.Clone().ControllerName("other-controller").Obj(),
			},
		},
		"should set Active status": {
			request:        baseRequest,
			admissionCheck: baseAdmissionCheckWrapper.DeepCopy(),
			wantAdmissionChecks: []kueue.AdmissionCheck{
				*baseAdmissionCheckWrapper.Clone().
					Condition(metav1.Condition{
						Type:               kueue.AdmissionCheckActive,
						Status:             metav1.ConditionTrue,
						Reason:             "Active",
						Message:            "The admission check is active",
						ObservedGeneration: baseGeneration,
					}).
					Obj(),
			},
		},
	}
	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			scheme := runtime.NewScheme()
			utilruntime.Must(kueue.AddToScheme(scheme))
			utilruntime.Must(kueue.AddToScheme(scheme))

			clientBuilder := fake.NewClientBuilder().WithScheme(scheme)

			if tc.admissionCheck != nil {
				clientBuilder = clientBuilder.WithObjects(tc.admissionCheck)
			}

			kClient := clientBuilder.Build()
			reconciler := NewAdmissionCheckReconciler(kClient)

			ctx, _ := utiltesting.ContextWithLog(t)

			_, err := reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: tc.request})
			if diff := cmp.Diff(tc.wantErr, err); diff != "" {
				t.Errorf("Error after reconcile (-want,+got):\n%s", diff)
			}
		})
	}
}
