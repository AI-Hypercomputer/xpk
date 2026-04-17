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

package leaderworkerset

import (
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/utils/ptr"
	leaderworkersetv1 "sigs.k8s.io/lws/api/leaderworkerset/v1"
)

type Wrapper struct {
	leaderworkersetv1.LeaderWorkerSet
}

func MakeLeaderWorkerSet(name, namespace string) *Wrapper {
	return &Wrapper{
		leaderworkersetv1.LeaderWorkerSet{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: namespace,
			},
		},
	}
}

func (w *Wrapper) Obj() *leaderworkersetv1.LeaderWorkerSet {
	return &w.LeaderWorkerSet
}

func (w *Wrapper) Queue(queue string) *Wrapper {
	if w.Labels == nil {
		w.Labels = make(map[string]string)
	}
	w.Labels["kueue.x-k8s.io/queue-name"] = queue
	return w
}

func (w *Wrapper) Size(size int32) *Wrapper {
	w.Spec.LeaderWorkerTemplate.Size = ptr.To[int32](size)
	return w
}

func (w *Wrapper) WorkerAnnotation(key, value string) *Wrapper {
	if w.Spec.LeaderWorkerTemplate.WorkerTemplate.Annotations == nil {
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Annotations = make(map[string]string)
	}
	w.Spec.LeaderWorkerTemplate.WorkerTemplate.Annotations[key] = value
	return w
}

func (w *Wrapper) WorkerNodeSelector(key, value string) *Wrapper {
	if w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.NodeSelector == nil {
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.NodeSelector = make(map[string]string)
	}
	w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.NodeSelector[key] = value
	return w
}

func (w *Wrapper) WorkerNodeAffinity(key string, values []string) *Wrapper {
	if w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Affinity == nil {
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Affinity = &corev1.Affinity{}
	}
	if w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Affinity.NodeAffinity == nil {
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Affinity.NodeAffinity = &corev1.NodeAffinity{}
	}
	if w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution == nil {
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution = &corev1.NodeSelector{}
	}
	w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms = append(
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms,
		corev1.NodeSelectorTerm{
			MatchExpressions: []corev1.NodeSelectorRequirement{
				{
					Key:      key,
					Operator: corev1.NodeSelectorOpIn,
					Values:   values,
				},
			},
		},
	)
	return w
}

func (w *Wrapper) WorkerLimit(resourceName corev1.ResourceName, quantity string) *Wrapper {
	if len(w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers) == 0 {
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers = []corev1.Container{{}}
	}
	if w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers[0].Resources.Limits == nil {
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers[0].Resources.Limits = make(corev1.ResourceList)
	}
	w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers[0].Resources.Limits[resourceName] = resource.MustParse(quantity)
	return w
}

func (w *Wrapper) WorkerRequestAndLimit(resourceName corev1.ResourceName, quantity string) *Wrapper {
	w.WorkerLimit(resourceName, quantity)
	if w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers[0].Resources.Requests == nil {
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers[0].Resources.Requests = make(corev1.ResourceList)
	}
	w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers[0].Resources.Requests[resourceName] = resource.MustParse(quantity)
	return w
}

func (w *Wrapper) WorkerImage(img string) *Wrapper {
	if len(w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers) == 0 {
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers = []corev1.Container{{}}
	}
	w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers[0].Image = img
	return w
}

func (w *Wrapper) WorkerArgs(args ...string) *Wrapper {
	if len(w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers) == 0 {
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers = []corev1.Container{{}}
	}
	w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers[0].Args = args
	return w
}

func (w *Wrapper) LeaderAnnotation(key, value string) *Wrapper {
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate = &corev1.PodTemplateSpec{}
	}
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate.Annotations == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Annotations = make(map[string]string)
	}
	w.Spec.LeaderWorkerTemplate.LeaderTemplate.Annotations[key] = value
	return w
}

func (w *Wrapper) LeaderNodeSelector(key, value string) *Wrapper {
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate = &corev1.PodTemplateSpec{}
	}
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.NodeSelector == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.NodeSelector = make(map[string]string)
	}
	w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.NodeSelector[key] = value
	return w
}

func (w *Wrapper) LeaderNodeAffinity(key string, values []string) *Wrapper {
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate = &corev1.PodTemplateSpec{}
	}
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Affinity == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Affinity = &corev1.Affinity{}
	}
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Affinity.NodeAffinity == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Affinity.NodeAffinity = &corev1.NodeAffinity{}
	}
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution = &corev1.NodeSelector{}
	}
	w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms = append(
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms,
		corev1.NodeSelectorTerm{
			MatchExpressions: []corev1.NodeSelectorRequirement{
				{
					Key:      key,
					Operator: corev1.NodeSelectorOpIn,
					Values:   values,
				},
			},
		},
	)
	return w
}

func (w *Wrapper) StartupPolicy(policy leaderworkersetv1.StartupPolicyType) *Wrapper {
	w.Spec.StartupPolicy = policy
	return w
}

func (w *Wrapper) WorkerName(name string) *Wrapper {
	if len(w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers) == 0 {
		w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers = []corev1.Container{{}}
	}
	w.Spec.LeaderWorkerTemplate.WorkerTemplate.Spec.Containers[0].Name = name
	return w
}

func (w *Wrapper) LeaderName(name string) *Wrapper {
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate = &corev1.PodTemplateSpec{}
	}
	if len(w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers) == 0 {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers = []corev1.Container{{}}
	}
	w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers[0].Name = name
	return w
}

func (w *Wrapper) LeaderImage(img string) *Wrapper {
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate = &corev1.PodTemplateSpec{}
	}
	if len(w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers) == 0 {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers = []corev1.Container{{}}
	}
	w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers[0].Image = img
	return w
}

func (w *Wrapper) LeaderArgs(args ...string) *Wrapper {
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate = &corev1.PodTemplateSpec{}
	}
	if len(w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers) == 0 {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers = []corev1.Container{{}}
	}
	w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers[0].Args = args
	return w
}

func (w *Wrapper) LeaderLimit(resourceName corev1.ResourceName, quantity string) *Wrapper {
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate = &corev1.PodTemplateSpec{}
	}
	if len(w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers) == 0 {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers = []corev1.Container{{}}
	}
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers[0].Resources.Limits == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers[0].Resources.Limits = make(corev1.ResourceList)
	}
	w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers[0].Resources.Limits[resourceName] = resource.MustParse(quantity)
	return w
}

func (w *Wrapper) LeaderRequestAndLimit(resourceName corev1.ResourceName, quantity string) *Wrapper {
	w.LeaderLimit(resourceName, quantity)
	if w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers[0].Resources.Requests == nil {
		w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers[0].Resources.Requests = make(corev1.ResourceList)
	}
	w.Spec.LeaderWorkerTemplate.LeaderTemplate.Spec.Containers[0].Resources.Requests[resourceName] = resource.MustParse(quantity)
	return w
}
