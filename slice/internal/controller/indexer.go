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
	"tpu-slice-controller/internal/util/slices"
)

const (
	OwnerReferenceUID = "metadata.ownerReferences.uid"
)

func indexOwnerReferenceUID(obj client.Object) []string {
	return slices.Map(obj.GetOwnerReferences(), func(o *metav1.OwnerReference) string { return string(o.UID) })
}

// SetupIndexer configures the indexer to index specific fields for kueue.Workload and v1alpha1.Slice resources.
func SetupIndexer(ctx context.Context, indexer client.FieldIndexer) error {
	if err := indexer.IndexField(ctx, &kueue.Workload{}, OwnerReferenceUID, indexOwnerReferenceUID); err != nil {
		return fmt.Errorf("setting index on ownerReferences.uid for Workload: %w", err)
	}
	if err := indexer.IndexField(ctx, &v1alpha1.Slice{}, OwnerReferenceUID, indexOwnerReferenceUID); err != nil {
		return fmt.Errorf("setting index on ownerReferences.uid for Slice: %w", err)
	}
	return nil
}
