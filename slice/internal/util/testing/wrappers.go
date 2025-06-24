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
	"time"
	"tpu-slice-controller/api/v1alpha1"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/ptr"
	"sigs.k8s.io/controller-runtime/pkg/client"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
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

type WorkloadWrapper struct{ kueue.Workload }

// MakeWorkload creates a wrapper for a Workload with a single pod
// with a single container.
func MakeWorkload(name, ns string) *WorkloadWrapper {
	return &WorkloadWrapper{kueue.Workload{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: ns},
	}}
}

func (w *WorkloadWrapper) Obj() *kueue.Workload {
	return &w.Workload
}

func (w *WorkloadWrapper) Clone() *WorkloadWrapper {
	return &WorkloadWrapper{Workload: *w.DeepCopy()}
}

func (w *WorkloadWrapper) UID(uid types.UID) *WorkloadWrapper {
	w.Workload.UID = uid
	return w
}

func (w *WorkloadWrapper) DeletionTimestamp(t time.Time) *WorkloadWrapper {
	w.Workload.DeletionTimestamp = ptr.To(metav1.NewTime(t).Rfc3339Copy())
	return w
}

func (w *WorkloadWrapper) Finalizers(fin ...string) *WorkloadWrapper {
	w.ObjectMeta.Finalizers = fin
	return w
}

func (w *WorkloadWrapper) Finished() *WorkloadWrapper {
	cond := metav1.Condition{
		Type:               kueue.WorkloadFinished,
		Status:             metav1.ConditionTrue,
		LastTransitionTime: metav1.Now(),
		Reason:             "ByTest",
		Message:            "Finished by test",
	}
	meta.SetStatusCondition(&w.Status.Conditions, cond)
	return w
}

func (w *WorkloadWrapper) Evicted() *WorkloadWrapper {
	cond := metav1.Condition{
		Type:               kueue.WorkloadEvicted,
		Status:             metav1.ConditionTrue,
		LastTransitionTime: metav1.Now(),
		Reason:             "ByTest",
		Message:            "Evicted by test",
	}
	meta.SetStatusCondition(&w.Status.Conditions, cond)
	return w
}

func (w *WorkloadWrapper) Active(a bool) *WorkloadWrapper {
	w.Spec.Active = ptr.To(a)
	return w
}

// SliceWrapper wraps a Slice.
type SliceWrapper struct {
	v1alpha1.Slice
}

func MakeSliceWrapper(name, namespace string) *SliceWrapper {
	return &SliceWrapper{
		v1alpha1.Slice{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: namespace,
			},
		},
	}
}

func (s *SliceWrapper) Clone() *SliceWrapper {
	return &SliceWrapper{Slice: *s.DeepCopy()}
}

func (s *SliceWrapper) Obj() *v1alpha1.Slice {
	return &s.Slice
}

func (s *SliceWrapper) ControllerReference(gvk schema.GroupVersionKind, name, uid string) *SliceWrapper {
	AppendOwnerReference(&s.Slice, gvk, name, uid, ptr.To(true), ptr.To(true))
	return s
}

func AppendOwnerReference(obj client.Object, gvk schema.GroupVersionKind, name, uid string, controller, blockDeletion *bool) {
	obj.SetOwnerReferences(append(obj.GetOwnerReferences(), metav1.OwnerReference{
		APIVersion:         gvk.GroupVersion().String(),
		Kind:               gvk.Kind,
		Name:               name,
		UID:                types.UID(uid),
		Controller:         controller,
		BlockOwnerDeletion: blockDeletion,
	}))
}
