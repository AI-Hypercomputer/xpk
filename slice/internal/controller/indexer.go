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
	"context"
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	"tpu-slice-controller/api/v1alpha1"
	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/util/slices"
)

const (
	// OwnerReferenceUID is an index key for owner references.
	OwnerReferenceUID = "metadata.ownerReferences.uid"
	// WorkloadNamespaceIndex is an index key for the workload namespace annotation.
	WorkloadNamespaceIndex = "workload.namespace"
	// WorkloadNameIndex is an index key for the workload name annotation.
	WorkloadNameIndex = "workload.name"
)

func indexOwnerReferenceUID(obj client.Object) []string {
	return slices.Map(obj.GetOwnerReferences(), func(o *metav1.OwnerReference) string { return string(o.UID) })
}

func indexSliceByWorkloadNamespace(obj client.Object) []string {
	if slice, ok := obj.(*v1alpha1.Slice); ok {
		if ns, found := slice.GetAnnotations()[core.OwnerWorkloadNamespaceAnnotation]; found {
			return []string{ns}
		}
	}
	return nil
}

func indexSliceByWorkloadName(obj client.Object) []string {
	if slice, ok := obj.(*v1alpha1.Slice); ok {
		if name, found := slice.GetAnnotations()[core.OwnerWorkloadNameAnnotation]; found {
			return []string{name}
		}
	}
	return nil
}

// SetupIndexer configures the indexer to index specific fields for kueue.Workload and v1alpha1.Slice resources.
func SetupIndexer(ctx context.Context, indexer client.FieldIndexer) error {
	if err := indexer.IndexField(ctx, &kueue.Workload{}, OwnerReferenceUID, indexOwnerReferenceUID); err != nil {
		return fmt.Errorf("setting index on ownerReferences.uid for Workload: %w", err)
	}
	// Since Slice is now cluster-scoped, it cannot have a controller owner reference to a namespaced Workload.
	// We use annotations for linking Slices to Workloads.
	if err := indexer.IndexField(ctx, &v1alpha1.Slice{}, WorkloadNamespaceIndex, indexSliceByWorkloadNamespace); err != nil {
		return fmt.Errorf("setting index on workload namespace for Slice: %w", err)
	}
	if err := indexer.IndexField(ctx, &v1alpha1.Slice{}, WorkloadNameIndex, indexSliceByWorkloadName); err != nil {
		return fmt.Errorf("setting index on workload name for Slice: %w", err)
	}
	return nil
}
