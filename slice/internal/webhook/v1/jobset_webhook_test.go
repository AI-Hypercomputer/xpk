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
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"k8s.io/apimachinery/pkg/util/validation/field"
	"k8s.io/utils/ptr"
	ctrl "sigs.k8s.io/controller-runtime"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"

	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"
	utiltesting "sigs.k8s.io/kueue/pkg/util/testing"
)

// JobTemplateWrapper wraps a JobTemplateSpec.
type JobTemplateWrapper struct {
	batchv1.JobTemplateSpec
}

// MakeJobTemplate creates a wrapper for a JobTemplateSpec.
func MakeJobTemplate(name, ns string) *JobTemplateWrapper {
	return &JobTemplateWrapper{
		batchv1.JobTemplateSpec{
			ObjectMeta: metav1.ObjectMeta{
				Name:        name,
				Namespace:   ns,
				Annotations: make(map[string]string),
			},
			Spec: batchv1.JobSpec{
				Template: corev1.PodTemplateSpec{
					Spec: corev1.PodSpec{},
				},
			},
		},
	}
}

// Obj returns the inner batchv1.JobTemplateSpec
func (j *JobTemplateWrapper) Obj() batchv1.JobTemplateSpec {
	return j.JobTemplateSpec
}

func (j *JobTemplateWrapper) SetAnnotation(key, value string) *JobTemplateWrapper {
	if j.Annotations == nil {
		j.Annotations = make(map[string]string)
	}
	j.Annotations[key] = value
	return j
}

func MakeJobSet(namespace string, labels map[string]string, replicatedJobs []jobset.ReplicatedJob) *jobset.JobSet {
	return &jobset.JobSet{
		Spec: jobset.JobSetSpec{
			ReplicatedJobs: replicatedJobs,
		},
		ObjectMeta: ctrl.ObjectMeta{
			Labels:    labels,
			Namespace: namespace,
		},
	}
}

func MakeReplicatedJob(name string, annotations map[string]string) jobset.ReplicatedJob {
	template := MakeJobTemplate(name, "").Obj()
	for key, value := range annotations {
		template.Annotations[key] = value
	}
	return jobset.ReplicatedJob{
		Name:     name,
		Template: template,
	}
}

const (
	DefaultNamespace   = "default"
	annotationValueTBD = "TBD"
)

func TestDefault(t *testing.T) {
	testCases := []struct {
		name    string
		jobSet  *jobset.JobSet
		want    *jobset.JobSet
		wantErr error
	}{
		{
			name: "TestDefault_No_Cluster_Queue_label",
			jobSet: &jobset.JobSet{
				Spec: jobset.JobSetSpec{
					ManagedBy: ptr.To(jobset.JobSetControllerName),
				},
				ObjectMeta: ctrl.ObjectMeta{
					Namespace: DefaultNamespace,
				},
			},
			want: &jobset.JobSet{
				Spec: jobset.JobSetSpec{
					ManagedBy: ptr.To(jobset.JobSetControllerName),
				},
				ObjectMeta: ctrl.ObjectMeta{
					Namespace: DefaultNamespace,
				},
			},
		},
		{
			name: "TestDefault_With_Cluster_Queue_label",
			jobSet: &jobset.JobSet{
				Spec: jobset.JobSetSpec{
					ReplicatedJobs: []jobset.ReplicatedJob{
						{
							Name:     "rj1",
							Template: MakeJobTemplate("rj1", "").Obj(),
						},
						{
							Name:     "rj2",
							Template: MakeJobTemplate("rj2", "").Obj(),
						},
					},
				},
				ObjectMeta: ctrl.ObjectMeta{
					Labels: map[string]string{
						kueueconstants.QueueLabel: "local-queue",
					},
					Namespace: DefaultNamespace,
				},
			},
			want: &jobset.JobSet{
				Spec: jobset.JobSetSpec{
					ReplicatedJobs: []jobset.ReplicatedJob{
						{
							Name: "rj1",
							Template: MakeJobTemplate("rj1", "").
								SetAnnotation(PodSetRequiredTopologyAnnotation, annotationValueTBD).
								SetAnnotation(PodSetSliceRequiredTopologyAnnotation, annotationValueTBD).
								SetAnnotation(PodSetSliceSizeAnnotation, annotationValueTBD).
								Obj(),
						},
						{
							Name: "rj2",
							Template: MakeJobTemplate("rj2", "").
								SetAnnotation(PodSetRequiredTopologyAnnotation, annotationValueTBD).
								SetAnnotation(PodSetSliceRequiredTopologyAnnotation, annotationValueTBD).
								SetAnnotation(PodSetSliceSizeAnnotation, annotationValueTBD).
								Obj(),
						},
					},
				},
				ObjectMeta: ctrl.ObjectMeta{
					Labels: map[string]string{
						kueueconstants.QueueLabel: "local-queue",
					},
					Namespace: DefaultNamespace,
				},
			},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			ctx, _ := utiltesting.ContextWithLog(t)
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

func TestValidateUpdate(t *testing.T) {
	testcases := []struct {
		name    string
		oldJob  *jobset.JobSet
		newJob  *jobset.JobSet
		wantErr field.ErrorList
	}{
		{
			name: "set valid topology request",
			oldJob: MakeJobSet(DefaultNamespace, map[string]string{
				kueueconstants.QueueLabel: "local-queue",
			}, []jobset.ReplicatedJob{
				MakeReplicatedJob("rj1", map[string]string{
					PodSetRequiredTopologyAnnotation:      annotationValueTBD,
					PodSetSliceRequiredTopologyAnnotation: annotationValueTBD,
					PodSetSliceSizeAnnotation:             annotationValueTBD,
				}),
				MakeReplicatedJob("rj2", map[string]string{
					PodSetRequiredTopologyAnnotation:      annotationValueTBD,
					PodSetSliceRequiredTopologyAnnotation: annotationValueTBD,
					PodSetSliceSizeAnnotation:             annotationValueTBD,
				}),
			}),
			newJob: MakeJobSet(DefaultNamespace, map[string]string{
				kueueconstants.QueueLabel: "local-queue",
			}, []jobset.ReplicatedJob{
				MakeReplicatedJob("rj1", map[string]string{
					PodSetRequiredTopologyAnnotation:      annotationValueTBD,
					PodSetSliceRequiredTopologyAnnotation: annotationValueTBD,
					PodSetSliceSizeAnnotation:             annotationValueTBD,
				}),
				MakeReplicatedJob("rj2", map[string]string{
					PodSetRequiredTopologyAnnotation:      annotationValueTBD,
					PodSetSliceRequiredTopologyAnnotation: annotationValueTBD,
					PodSetSliceSizeAnnotation:             annotationValueTBD,
				}),
			}),
			wantErr: nil,
		},
		{
			name: "attempt to set invalid topology request",
			// This test ensures that modifying the PodSetRequiredTopologyAnnotation to an empty value
			// is flagged as an error because the field is immutable.
			oldJob: MakeJobSet(DefaultNamespace, map[string]string{
				kueueconstants.QueueLabel: "local-queue",
			}, []jobset.ReplicatedJob{
				MakeReplicatedJob("rj1", map[string]string{
					PodSetRequiredTopologyAnnotation:      annotationValueTBD,
					PodSetSliceRequiredTopologyAnnotation: annotationValueTBD,
					PodSetSliceSizeAnnotation:             annotationValueTBD,
				}),
				MakeReplicatedJob("rj2", map[string]string{
					PodSetRequiredTopologyAnnotation:      annotationValueTBD,
					PodSetSliceRequiredTopologyAnnotation: annotationValueTBD,
					PodSetSliceSizeAnnotation:             annotationValueTBD,
				}),
			}),
			newJob: MakeJobSet(DefaultNamespace, map[string]string{
				kueueconstants.QueueLabel: "local-queue",
			}, []jobset.ReplicatedJob{
				MakeReplicatedJob("rj1", map[string]string{
					PodSetRequiredTopologyAnnotation:      annotationValueTBD,
					PodSetSliceRequiredTopologyAnnotation: annotationValueTBD,
					PodSetSliceSizeAnnotation:             annotationValueTBD,
				}),
				MakeReplicatedJob("rj2", map[string]string{
					PodSetRequiredTopologyAnnotation:      "",
					PodSetSliceRequiredTopologyAnnotation: "random value",
					PodSetSliceSizeAnnotation:             annotationValueTBD,
				}),
			}),
			wantErr: field.ErrorList{
				field.Invalid(
					annotationsPath.Key(PodSetRequiredTopologyAnnotation),
					string(""),
					`field is immutable`,
				),
				field.Invalid(
					annotationsPath.Key(PodSetSliceRequiredTopologyAnnotation),
					string("random value"),
					`field is immutable`,
				),
			},
		},
	}

	for _, tc := range testcases {
		t.Run(tc.name, func(t *testing.T) {
			ctx, _ := utiltesting.ContextWithLog(t)
			webhook := &JobSetWebhook{}

			_, gotErr := webhook.ValidateUpdate(ctx, tc.oldJob, tc.newJob)
			if diff := cmp.Diff(tc.wantErr.ToAggregate(), gotErr, cmpopts.IgnoreFields(field.Error{})); diff != "" {
				t.Errorf("validateUpdate() mismatch (-want +got):\n%s", diff)
			}
		})
	}
}
