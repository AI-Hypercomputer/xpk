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

package testing

import (
	"time"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/ptr"
	"sigs.k8s.io/controller-runtime/pkg/client"
	kueuealpha "sigs.k8s.io/kueue/apis/kueue/v1alpha1"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	"tpu-slice-controller/api/v1alpha1"
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

// PodSetAssignments sets the PodSetAssignments for the workload.
func (w *WorkloadWrapper) PodSetAssignments(assignments ...kueue.PodSetAssignment) *WorkloadWrapper {
	if w.Status.Admission == nil {
		w.Status.Admission = &kueue.Admission{
			PodSetAssignments: make([]kueue.PodSetAssignment, 0, len(assignments)),
		}
	}
	w.Status.Admission.PodSetAssignments = assignments
	return w
}

type PodSetAssignmentWrapper struct {
	kueue.PodSetAssignment
}

func MakePodSetAssignment(name string) *PodSetAssignmentWrapper {
	return &PodSetAssignmentWrapper{
		kueue.PodSetAssignment{
			Name: kueue.NewPodSetReference(name),
		},
	}
}

func (w *PodSetAssignmentWrapper) TopologyAssignment(levels []string, domains []kueue.TopologyDomainAssignment) *PodSetAssignmentWrapper {
	if w.PodSetAssignment.TopologyAssignment == nil {
		w.PodSetAssignment.TopologyAssignment = &kueue.TopologyAssignment{
			Levels:  make([]string, len(levels)),
			Domains: make([]kueue.TopologyDomainAssignment, 0, len(domains)),
		}
	}
	w.PodSetAssignment.TopologyAssignment.Levels = append(w.PodSetAssignment.TopologyAssignment.Levels, levels...)
	w.PodSetAssignment.TopologyAssignment.Domains = append(w.PodSetAssignment.TopologyAssignment.Domains, domains...)
	return w
}

func (w *PodSetAssignmentWrapper) Obj() kueue.PodSetAssignment {
	return w.PodSetAssignment
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

func (s *SliceWrapper) NodeSelector(ns map[string][]string) *SliceWrapper {
	s.Spec.NodeSelector = ns
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

type NamespaceWrapper struct {
	corev1.Namespace
}

func MakeNamespaceWrapper(name string) *NamespaceWrapper {
	return &NamespaceWrapper{
		corev1.Namespace{
			ObjectMeta: metav1.ObjectMeta{
				Name: name,
			},
		},
	}
}

func (w *NamespaceWrapper) GenerateName(generateName string) *NamespaceWrapper {
	w.Namespace.GenerateName = generateName
	return w
}

func (w *NamespaceWrapper) Obj() *corev1.Namespace {
	return &w.Namespace
}

// MakeNamespaceWithGenerateName creates a default namespace with generate name.
func MakeNamespaceWithGenerateName(prefix string) *corev1.Namespace {
	return MakeNamespaceWrapper("").GenerateName(prefix).Obj()
}

// ResourceFlavorWrapper wraps a ResourceFlavor.
type ResourceFlavorWrapper struct{ kueue.ResourceFlavor }

// MakeResourceFlavor creates a wrapper for a ResourceFlavor.
func MakeResourceFlavor(name string) *ResourceFlavorWrapper {
	return &ResourceFlavorWrapper{kueue.ResourceFlavor{
		ObjectMeta: metav1.ObjectMeta{
			Name: name,
		},
		Spec: kueue.ResourceFlavorSpec{
			NodeLabels: make(map[string]string),
		},
	}}
}

// Obj returns the inner ResourceFlavor.
func (rf *ResourceFlavorWrapper) Obj() *kueue.ResourceFlavor {
	return &rf.ResourceFlavor
}

// TopologyName sets the topology name
func (rf *ResourceFlavorWrapper) TopologyName(name string) *ResourceFlavorWrapper {
	rf.Spec.TopologyName = ptr.To(kueue.TopologyReference(name))
	return rf
}

// NodeLabel add a label kueue and value pair to the ResourceFlavor.
func (rf *ResourceFlavorWrapper) NodeLabel(k, v string) *ResourceFlavorWrapper {
	rf.Spec.NodeLabels[k] = v
	return rf
}

// ClusterQueueWrapper wraps a ClusterQueue.
type ClusterQueueWrapper struct{ kueue.ClusterQueue }

// MakeClusterQueue creates a wrapper for a ClusterQueue with a
// select-all NamespaceSelector.
func MakeClusterQueue(name string) *ClusterQueueWrapper {
	return &ClusterQueueWrapper{kueue.ClusterQueue{
		ObjectMeta: metav1.ObjectMeta{
			Name: name,
		},
		Spec: kueue.ClusterQueueSpec{
			NamespaceSelector: &metav1.LabelSelector{},
			QueueingStrategy:  kueue.BestEffortFIFO,
			FlavorFungibility: &kueue.FlavorFungibility{
				WhenCanBorrow:  kueue.Borrow,
				WhenCanPreempt: kueue.TryNextFlavor,
			},
		},
	}}
}

// Obj returns the inner ClusterQueue.
func (c *ClusterQueueWrapper) Obj() *kueue.ClusterQueue {
	return &c.ClusterQueue
}

// ResourceGroup creates a ResourceGroup with the given FlavorQuotas.
func ResourceGroup(flavors ...kueue.FlavorQuotas) kueue.ResourceGroup {
	rg := kueue.ResourceGroup{
		Flavors: flavors,
	}
	if len(flavors) > 0 {
		var resources []corev1.ResourceName
		for _, r := range flavors[0].Resources {
			resources = append(resources, r.Name)
		}
		for i := 1; i < len(flavors); i++ {
			if len(flavors[i].Resources) != len(resources) {
				panic("Must list the same resources in all flavors in a ResourceGroup")
			}
			for j, r := range flavors[i].Resources {
				if r.Name != resources[j] {
					panic("Must list the same resources in all flavors in a ResourceGroup")
				}
			}
		}
		rg.CoveredResources = resources
	}
	return rg
}

// ResourceGroup adds a ResourceGroup with flavors.
func (c *ClusterQueueWrapper) ResourceGroup(flavors ...kueue.FlavorQuotas) *ClusterQueueWrapper {
	c.Spec.ResourceGroups = append(c.Spec.ResourceGroups, ResourceGroup(flavors...))
	return c
}

// FlavorQuotasWrapper wraps a FlavorQuotas object.
type FlavorQuotasWrapper struct{ kueue.FlavorQuotas }

// MakeFlavorQuotas creates a wrapper for a resource flavor.
func MakeFlavorQuotas(name string) *FlavorQuotasWrapper {
	return &FlavorQuotasWrapper{kueue.FlavorQuotas{
		Name: kueue.ResourceFlavorReference(name),
	}}
}

// Obj returns the inner flavor.
func (f *FlavorQuotasWrapper) Obj() *kueue.FlavorQuotas {
	return &f.FlavorQuotas
}

// Resource takes ResourceName, followed by the optional NominalQuota, BorrowingLimit, LendingLimit.
func (f *FlavorQuotasWrapper) Resource(name corev1.ResourceName, qs ...string) *FlavorQuotasWrapper {
	resourceWrapper := f.ResourceQuotaWrapper(name)
	if len(qs) > 0 {
		resourceWrapper.NominalQuota(qs[0])
	}
	if len(qs) > 1 && len(qs[1]) > 0 {
		resourceWrapper.BorrowingLimit(qs[1])
	}
	if len(qs) > 2 && len(qs[2]) > 0 {
		resourceWrapper.LendingLimit(qs[2])
	}
	if len(qs) > 3 {
		panic("Must have at most 3 quantities for nominalQuota, borrowingLimit and lendingLimit")
	}
	return resourceWrapper.Append()
}

// ResourceQuotaWrapper allows creation the creation of a Resource in a type-safe manner.
func (f *FlavorQuotasWrapper) ResourceQuotaWrapper(name corev1.ResourceName) *ResourceQuotaWrapper {
	rq := kueue.ResourceQuota{
		Name: name,
	}
	return &ResourceQuotaWrapper{parent: f, ResourceQuota: rq}
}

// ResourceQuotaWrapper wraps a ResourceQuota object.
type ResourceQuotaWrapper struct {
	parent *FlavorQuotasWrapper
	kueue.ResourceQuota
}

func (rq *ResourceQuotaWrapper) NominalQuota(quantity string) *ResourceQuotaWrapper {
	rq.ResourceQuota.NominalQuota = resource.MustParse(quantity)
	return rq
}

func (rq *ResourceQuotaWrapper) BorrowingLimit(quantity string) *ResourceQuotaWrapper {
	rq.ResourceQuota.BorrowingLimit = ptr.To(resource.MustParse(quantity))
	return rq
}

func (rq *ResourceQuotaWrapper) LendingLimit(quantity string) *ResourceQuotaWrapper {
	rq.ResourceQuota.LendingLimit = ptr.To(resource.MustParse(quantity))
	return rq
}

// Append appends the ResourceQuotaWrapper to its parent
func (rq *ResourceQuotaWrapper) Append() *FlavorQuotasWrapper {
	rq.parent.Resources = append(rq.parent.Resources, rq.ResourceQuota)
	return rq.parent
}

// LocalQueueWrapper wraps a Queue.
type LocalQueueWrapper struct{ kueue.LocalQueue }

// MakeLocalQueue creates a wrapper for a LocalQueue.
func MakeLocalQueue(name, ns string) *LocalQueueWrapper {
	return &LocalQueueWrapper{kueue.LocalQueue{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: ns,
		},
	}}
}

// Obj returns the inner LocalQueue.
func (q *LocalQueueWrapper) Obj() *kueue.LocalQueue {
	return &q.LocalQueue
}

// ClusterQueue updates the clusterQueue the queue points to.
func (q *LocalQueueWrapper) ClusterQueue(c string) *LocalQueueWrapper {
	q.Spec.ClusterQueue = kueue.ClusterQueueReference(c)
	return q
}

// TopologyWrapper wraps a Topology.
type TopologyWrapper struct{ kueuealpha.Topology }

// MakeTopology creates a wrapper for a Topology.
func MakeTopology(name string) *TopologyWrapper {
	return &TopologyWrapper{kueuealpha.Topology{
		ObjectMeta: metav1.ObjectMeta{
			Name: name,
		},
	}}
}

// Levels sets the levels for a Topology.
func (t *TopologyWrapper) Levels(levels ...string) *TopologyWrapper {
	t.Spec.Levels = make([]kueuealpha.TopologyLevel, len(levels))
	for i, level := range levels {
		t.Spec.Levels[i] = kueuealpha.TopologyLevel{
			NodeLabel: level,
		}
	}
	return t
}

func (t *TopologyWrapper) Obj() *kueuealpha.Topology {
	return &t.Topology
}
