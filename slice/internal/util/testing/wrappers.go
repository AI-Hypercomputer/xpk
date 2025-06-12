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
package testing

import (
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	ctrl "sigs.k8s.io/controller-runtime"

	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
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
