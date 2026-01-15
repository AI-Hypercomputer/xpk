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

package core

import (
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
)

func BaseSSAJobSet(js *jobset.JobSet) *jobset.JobSet {
	return &jobset.JobSet{
		TypeMeta: metav1.TypeMeta{
			APIVersion: jobset.SchemeGroupVersion.String(),
			Kind:       "JobSet",
		},
		ObjectMeta: metav1.ObjectMeta{
			Name:      js.Name,
			Namespace: js.Namespace,
			UID:       js.UID,
		},
		Spec: jobset.JobSetSpec{
			ReplicatedJobs: make([]jobset.ReplicatedJob, len(js.Spec.ReplicatedJobs)),
		},
	}
}

func BaseSSAReplicatedJob(name string) jobset.ReplicatedJob {
	return jobset.ReplicatedJob{
		Name: name,
		Template: batchv1.JobTemplateSpec{
			Spec: batchv1.JobSpec{
				Template: corev1.PodTemplateSpec{
					Spec: corev1.PodSpec{
						NodeSelector: make(map[string]string),
					},
				},
			},
		},
	}
}
