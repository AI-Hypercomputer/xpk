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
	"errors"
	"testing"

	"github.com/google/go-cmp/cmp"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/utils/ptr"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/core"
	utiltesting "tpu-slice-controller/internal/util/testing"
)

type JobWrapper struct {
	batchv1.Job
}

func MakeJob(name, ns string) *JobWrapper {
	return &JobWrapper{
		Job: batchv1.Job{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: ns,
			},
			Spec: batchv1.JobSpec{
				Template: corev1.PodTemplateSpec{
					Spec: corev1.PodSpec{
						RestartPolicy: corev1.RestartPolicyNever,
						Containers: []corev1.Container{
							{
								Name:  "c",
								Image: "pause",
							},
						},
					},
				},
			},
		},
	}
}

func (j *JobWrapper) Obj() *batchv1.Job {
	return &j.Job
}

func (j *JobWrapper) Queue(q string) *JobWrapper {
	if j.Labels == nil {
		j.Labels = make(map[string]string)
	}
	j.Labels[kueueconstants.QueueLabel] = q
	return j
}

func (j *JobWrapper) Parallelism(p int32) *JobWrapper {
	j.Spec.Parallelism = ptr.To(p)
	return j
}

func (j *JobWrapper) PodAnnotation(k, v string) *JobWrapper {
	if j.Spec.Template.Annotations == nil {
		j.Spec.Template.Annotations = make(map[string]string)
	}
	j.Spec.Template.Annotations[k] = v
	return j
}

func (j *JobWrapper) NodeSelector(k, v string) *JobWrapper {
	if j.Spec.Template.Spec.NodeSelector == nil {
		j.Spec.Template.Spec.NodeSelector = make(map[string]string)
	}
	j.Spec.Template.Spec.NodeSelector[k] = v
	return j
}

func (j *JobWrapper) Request(r corev1.ResourceName, v string) *JobWrapper {
	if j.Spec.Template.Spec.Containers[0].Resources.Limits == nil {
		j.Spec.Template.Spec.Containers[0].Resources.Limits = make(corev1.ResourceList)
	}
	j.Spec.Template.Spec.Containers[0].Resources.Limits[r] = resource.MustParse(v)
	return j
}

func (j *JobWrapper) NodeAffinity(key string, values []string) *JobWrapper {
	core.AddNodeAffinity(&j.Spec.Template, key, values)
	return j
}

func TestJobDefault(t *testing.T) {
	const (
		baseJobName   = "job"
		baseNamespace = "default"
	)

	testCases := map[string]struct {
		job     *batchv1.Job
		wantJob *batchv1.Job
		wantErr error
	}{
		"no queue label": {
			job: MakeJob(baseJobName, baseNamespace).
				Parallelism(48).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x12").
				NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Obj(),
			wantJob: MakeJob(baseJobName, baseNamespace).
				Parallelism(48).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x12").
				NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Obj(),
		},
		"no tpu topology annotation": {
			job: MakeJob(baseJobName, baseNamespace).
				Queue("queue-name").
				Parallelism(48).
				NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Obj(),
			wantJob: MakeJob(baseJobName, baseNamespace).
				Queue("queue-name").
				Parallelism(48).
				NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Obj(),
		},
		"no tpu accelerator node selector label": {
			job: MakeJob(baseJobName, baseNamespace).
				Queue("queue-name").
				Parallelism(48).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x12").
				Obj(),
			wantJob: MakeJob(baseJobName, baseNamespace).
				Queue("queue-name").
				Parallelism(48).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x12").
				Obj(),
		},
		"should set default values": {
			job: MakeJob(baseJobName, baseNamespace).
				Queue("queue-name").
				Parallelism(48).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x12").
				NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Request(core.TPUResourceName, "4").
				Obj(),
			wantJob: MakeJob(baseJobName, baseNamespace).
				Queue("queue-name").
				Parallelism(48).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x12").
				PodAnnotation(kueue.PodSetRequiredTopologyAnnotation, core.TPUBlockLabel).
				PodAnnotation(kueue.PodSetSliceRequiredTopologyAnnotation, core.TPUSubBlockLabel).
				PodAnnotation(kueue.PodSetSliceSizeAnnotation, "16").
				NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Request(core.TPUResourceName, "4").
				NodeAffinity(core.TPUSliceHealthNodeSelectorKey, []string{core.TPUSliceHealthNodeSelectorHealthy}).
				Obj(),
		},
		"should respect existing NodeSelector for health": {
			job: MakeJob(baseJobName, baseNamespace).
				Queue("queue-name").
				Parallelism(48).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x12").
				NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				NodeSelector(core.TPUSliceHealthNodeSelectorKey, "HEALTHY").
				Request(core.TPUResourceName, "4").
				Obj(),
			wantJob: MakeJob(baseJobName, baseNamespace).
				Queue("queue-name").
				Parallelism(48).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x12").
				PodAnnotation(kueue.PodSetRequiredTopologyAnnotation, core.TPUBlockLabel).
				PodAnnotation(kueue.PodSetSliceRequiredTopologyAnnotation, core.TPUSubBlockLabel).
				PodAnnotation(kueue.PodSetSliceSizeAnnotation, "16").
				NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				NodeSelector(core.TPUSliceHealthNodeSelectorKey, "HEALTHY").
				Request(core.TPUResourceName, "4").
				Obj(),
		},
		"should respect existing NodeAffinity for health": {
			job: MakeJob(baseJobName, baseNamespace).
				Queue("queue-name").
				Parallelism(48).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x12").
				NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				NodeAffinity(core.TPUSliceHealthNodeSelectorKey, []string{"HEALTHY", "DEGRADED"}).
				Request(core.TPUResourceName, "4").
				Obj(),
			wantJob: MakeJob(baseJobName, baseNamespace).
				Queue("queue-name").
				Parallelism(48).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x12").
				PodAnnotation(kueue.PodSetRequiredTopologyAnnotation, core.TPUBlockLabel).
				PodAnnotation(kueue.PodSetSliceRequiredTopologyAnnotation, core.TPUSubBlockLabel).
				PodAnnotation(kueue.PodSetSliceSizeAnnotation, "16").
				NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				NodeAffinity(core.TPUSliceHealthNodeSelectorKey, []string{"HEALTHY", "DEGRADED"}).
				Request(core.TPUResourceName, "4").
				Obj(),
		},
		"should reject incorrectly configured job not utilizing entire cube; single cube": {
			job: MakeJob(baseJobName, baseNamespace).
				Queue("queue-name").
				Parallelism(16).
				PodAnnotation(core.TPUSliceTopologyAnnotation, "4x4x4").
				NodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Request(core.TPUResourceName, "1").
				Obj(),
			wantErr: errors.New("invalid job \"job\": configuration results in 16 TPUs requested per cube, but must be exactly 64 TPUs (full utilization)"),
		},
	}

	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			ctx := t.Context()
			webhook := &JobWebhook{}

			gotErr := webhook.Default(ctx, tc.job)
			if diff := cmp.Diff(tc.wantErr, gotErr, utiltesting.EquateErrors); diff != "" {
				t.Errorf("Default() error mismatch (-want +got):\n%s", diff)
			}
			if tc.wantJob != nil {
				if diff := cmp.Diff(tc.wantJob, tc.job); diff != "" {
					t.Errorf("Default() mismatch (-want,+got):\n%s", diff)
				}
			}
		})
	}
}
