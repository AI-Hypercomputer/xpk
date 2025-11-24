// Copyright The Kubernetes Authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package core

import (
	"fmt"
	"time"

	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	"tpu-slice-controller/api/v1alpha1"
)

const (
	activationTimeout = 3 * time.Minute
)

func SliceKeyFromWorkload(wl *kueue.Workload, podSetName kueue.PodSetReference) client.ObjectKey {
	slice := SliceWithMetadata(wl, podSetName)
	return client.ObjectKeyFromObject(slice)
}

func SliceWithMetadata(wl *kueue.Workload, podSetName kueue.PodSetReference) *v1alpha1.Slice {
	return &v1alpha1.Slice{
		ObjectMeta: metav1.ObjectMeta{
			Name: SliceName(wl.Namespace, wl.Name, podSetName),
			Annotations: map[string]string{
				OwnerWorkloadNamespaceAnnotation: wl.Namespace,
				OwnerWorkloadNameAnnotation:      wl.Name,
			},
		},
	}
}

func SliceName(ns string, workloadName string, podSetName kueue.PodSetReference) string {
	return fmt.Sprintf("%s-%s-%s", ns, workloadName, podSetName)
}

func isStale(slice *v1alpha1.Slice) bool {
	cond := meta.FindStatusCondition(slice.Status.Conditions, v1alpha1.SliceStateConditionType)
	staleUnready := cond != nil && cond.Status == metav1.ConditionFalse && !cond.LastTransitionTime.IsZero() && time.Since(cond.LastTransitionTime.Time) >= activationTimeout
	staleWithoutState := cond == nil && !slice.CreationTimestamp.IsZero() && time.Since(slice.CreationTimestamp.Time) >= activationTimeout
	return staleUnready || staleWithoutState
}

func isError(slice *v1alpha1.Slice) bool {
	condReady := meta.FindStatusCondition(slice.Status.Conditions, v1alpha1.SliceStateConditionType)
	condFailed := meta.FindStatusCondition(slice.Status.Conditions, v1alpha1.SliceCreationFailedConditionType)
	runtimeError := condReady != nil && condReady.Status == metav1.ConditionFalse && condReady.Reason == string(MMIGHealthStatusFailed)
	creationError := condFailed != nil && condFailed.Status == metav1.ConditionTrue
	return runtimeError || creationError
}
