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

package webhooks

import (
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/utils/ptr"
	ctrl "sigs.k8s.io/controller-runtime"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"

	utiltesting "tpu-slice-controller/internal/util/testing"
)

func TestDefault(t *testing.T) {
	testCases := []struct {
		name    string
		jobSet  *jobset.JobSet
		want    *jobset.JobSet
		wantErr error
	}{
		{
			name: "TestDefault_No_Local_Queue_label",
			jobSet: &jobset.JobSet{
				Spec: jobset.JobSetSpec{
					ManagedBy: ptr.To(jobset.JobSetControllerName),
				},
				ObjectMeta: ctrl.ObjectMeta{
					Namespace: metav1.NamespaceDefault,
				},
			},
			want: &jobset.JobSet{
				Spec: jobset.JobSetSpec{
					ManagedBy: ptr.To(jobset.JobSetControllerName),
				},
				ObjectMeta: ctrl.ObjectMeta{
					Namespace: metav1.NamespaceDefault,
				},
			},
		},
		{
			name: "TestDefault_With_Local_Queue_label",
			jobSet: &jobset.JobSet{
				Spec: jobset.JobSetSpec{
					ReplicatedJobs: []jobset.ReplicatedJob{
						{
							Name:     "rj1",
							Template: utiltesting.MakeJobTemplate("rj1", "").Obj(),
						},
						{
							Name:     "rj2",
							Template: utiltesting.MakeJobTemplate("rj2", "").Obj(),
						},
					},
				},
				ObjectMeta: ctrl.ObjectMeta{
					Labels: map[string]string{
						kueueconstants.QueueLabel: "local-queue",
					},
					Namespace: metav1.NamespaceDefault,
				},
			},
			want: &jobset.JobSet{
				Spec: jobset.JobSetSpec{
					ReplicatedJobs: []jobset.ReplicatedJob{
						{
							Name: "rj1",
							Template: utiltesting.MakeJobTemplate("rj1", "").
								SetAnnotation(PodSetRequiredTopologyAnnotation, AnnotationValueTBD).
								SetAnnotation(PodSetSliceRequiredTopologyAnnotation, AnnotationValueTBD).
								SetAnnotation(PodSetSliceSizeAnnotation, AnnotationValueTBD).
								Obj(),
						},
						{
							Name: "rj2",
							Template: utiltesting.MakeJobTemplate("rj2", "").
								SetAnnotation(PodSetRequiredTopologyAnnotation, AnnotationValueTBD).
								SetAnnotation(PodSetSliceRequiredTopologyAnnotation, AnnotationValueTBD).
								SetAnnotation(PodSetSliceSizeAnnotation, AnnotationValueTBD).
								Obj(),
						},
					},
				},
				ObjectMeta: ctrl.ObjectMeta{
					Labels: map[string]string{
						kueueconstants.QueueLabel: "local-queue",
					},
					Namespace: metav1.NamespaceDefault,
				},
			},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			ctx := t.Context()
			webhook := &JobSetWebhook{}

			gotErr := webhook.Default(ctx, tc.jobSet)
			if diff := cmp.Diff(tc.wantErr, gotErr, cmpopts.EquateErrors()); diff != "" {
				t.Errorf("Default() error mismatch (-want +got):\n%s", diff)
			}
			if tc.want != nil {
				if diff := cmp.Diff(tc.want, tc.jobSet); diff != "" {
					t.Errorf("Default() mismatch (-want,+got):\n%s", diff)
				}
			}
		})
	}
}
