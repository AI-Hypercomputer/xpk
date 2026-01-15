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
	"regexp"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"tpu-slice-controller/api/v1beta1"
)

type MMIGHealthStatus string
type SliceState string

var SliceStates = []SliceState{
	SliceStateCreated, SliceStateActivating, SliceStateActive, SliceStateActiveDegraded,
	SliceStateFailed, SliceStateDeleted, SliceStateStale,
}

func IsValidTPUTopology(tpuTopology string) bool {
	validTopology, _ := regexp.MatchString("[0-9]+x[0-9]+x[0-9]+", tpuTopology)
	return validTopology
}

func IsValidTPUAccelerator(tpuAccelerator string) bool {
	return tpuAccelerator == string(v1beta1.TypeTpu7x)
}

func IsRelevantPodTemplateSpec(spec corev1.PodTemplateSpec) bool {
	return IsValidTPUTopology(GetTPUTopology(spec)) &&
		IsValidTPUAccelerator(GetTPUAccelerator(spec))
}

func GetTPUTopology(spec corev1.PodTemplateSpec) string {
	return spec.Annotations[TPUSliceTopologyAnnotation]
}

func GetTPUAccelerator(spec corev1.PodTemplateSpec) string {
	if val, ok := spec.Spec.NodeSelector[TPUAcceleratorLabel]; ok {
		return val
	}
	if spec.Spec.Affinity != nil && spec.Spec.Affinity.NodeAffinity != nil && spec.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution != nil {
		for _, term := range spec.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms {
			for _, matchExpression := range term.MatchExpressions {
				if matchExpression.Key == TPUAcceleratorLabel && matchExpression.Operator == corev1.NodeSelectorOpIn {
					if len(matchExpression.Values) > 0 {
						return matchExpression.Values[0]
					}
				}
			}
		}
	}
	return ""
}

func GetSliceState(slice v1beta1.Slice, timeout time.Duration) SliceState {
	if !slice.DeletionTimestamp.IsZero() {
		return SliceStateDeleted
	}
	if isError(&slice) {
		return SliceStateFailed
	}
	if isStale(&slice, timeout) {
		return SliceStateStale
	}
	condReady := meta.FindStatusCondition(slice.Status.Conditions, v1beta1.SliceStateConditionType)
	if condReady != nil && condReady.Status == metav1.ConditionTrue {
		if condReady.Reason == string(MMIGHealthStatusActive) {
			return SliceStateActive
		}
		if condReady.Reason == string(MMIGHealthStatusActiveDegraded) {
			return SliceStateActiveDegraded
		}
	}
	if condReady == nil {
		return SliceStateCreated
	}
	return SliceStateActivating
}
