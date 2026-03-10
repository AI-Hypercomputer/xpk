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

package job

import (
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/utils/ptr"
	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"

	"tpu-slice-controller/internal/core"
)

// JobWrapper wraps a Job.
type JobWrapper struct {
	batchv1.Job
}

// MakeJob creates a wrapper for a Job
func MakeJob(name, ns string) *JobWrapper {
	return &JobWrapper{
		Job: batchv1.Job{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: ns,
			},
			Spec: batchv1.JobSpec{
				Suspend: ptr.To(true),
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

// Obj returns the inner Job.
func (j *JobWrapper) Obj() *batchv1.Job {
	return &j.Job
}

// Queue updates the queue name of the Job.
func (j *JobWrapper) Queue(queue string) *JobWrapper {
	if j.Labels == nil {
		j.Labels = make(map[string]string)
	}
	j.Labels[kueueconstants.QueueLabel] = queue
	return j
}

func (j *JobWrapper) Parallelism(p int32) *JobWrapper {
	j.Spec.Parallelism = ptr.To(p)
	return j
}

func (j *JobWrapper) Completions(p int32) *JobWrapper {
	j.Spec.Completions = ptr.To(p)
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
	if j.Spec.Template.Spec.Containers[0].Resources.Requests == nil {
		j.Spec.Template.Spec.Containers[0].Resources.Requests = make(corev1.ResourceList)
	}
	j.Spec.Template.Spec.Containers[0].Resources.Requests[r] = resource.MustParse(v)
	return j
}

func (j *JobWrapper) Limit(r corev1.ResourceName, v string) *JobWrapper {
	if j.Spec.Template.Spec.Containers[0].Resources.Limits == nil {
		j.Spec.Template.Spec.Containers[0].Resources.Limits = make(corev1.ResourceList)
	}
	j.Spec.Template.Spec.Containers[0].Resources.Limits[r] = resource.MustParse(v)
	return j
}

func (j *JobWrapper) RequestAndLimit(r corev1.ResourceName, v string) *JobWrapper {
	return j.Request(r, v).Limit(r, v)
}

func (j *JobWrapper) Image(img string) *JobWrapper {
	j.Spec.Template.Spec.Containers[0].Image = img
	return j
}

func (j *JobWrapper) Args(args ...string) *JobWrapper {
	j.Spec.Template.Spec.Containers[0].Args = args
	return j
}

func (j *JobWrapper) NodeAffinity(key string, values []string) *JobWrapper {
	core.AddNodeAffinity(&j.Spec.Template, key, corev1.NodeSelectorOpIn, values)
	return j
}
