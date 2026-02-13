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
	"fmt"
	"regexp"
	"strconv"
	"strings"
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

func IsRelevantTPUTopology(tpuTopology string) bool {
	validTopology, _ := regexp.MatchString("[0-9]+x[0-9]+x[0-9]+", tpuTopology)
	return validTopology
}

func IsValidTPUAccelerator(tpuAccelerator string) bool {
	return tpuAccelerator == string(v1beta1.TypeTpu7x)
}

func IsRelevantPodTemplateSpec(spec corev1.PodTemplateSpec) bool {
	return IsRelevantTPUTopology(GetTPUTopology(spec)) &&
		IsValidTPUAccelerator(GetTPUAccelerator(spec))
}

func GetTPUTopology(spec corev1.PodTemplateSpec) string {
	return spec.Annotations[TPUSliceTopologyAnnotation]
}

func GetTPUAccelerator(spec corev1.PodTemplateSpec) string {
	if val, ok := spec.Spec.NodeSelector[TPUAcceleratorLabel]; ok {
		return val
	}
	if val, ok := getTPUAcceleratorFromAffinity(spec.Spec.Affinity); ok {
		return val
	}
	return ""
}

func getTPUAcceleratorFromAffinity(affinity *corev1.Affinity) (string, bool) {
	if affinity != nil && affinity.NodeAffinity != nil && affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution != nil {
		for _, term := range affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms {
			for _, matchExpression := range term.MatchExpressions {
				if matchExpression.Key == TPUAcceleratorLabel && matchExpression.Operator == corev1.NodeSelectorOpIn && len(matchExpression.Values) == 1 {
					return matchExpression.Values[0], true
				}
			}
		}
	}
	return "", false
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

type TopologyType int

const (
	TopologyTypeInvalid TopologyType = iota
	TopologyTypeSuperslice
	TopologyTypeSubslice
)

func ParseTopology(tpuTopology string) ([]int64, TopologyType, error) {
	dimensions := strings.Split(tpuTopology, "x")
	if len(dimensions) != 3 {
		return nil, TopologyTypeInvalid, fmt.Errorf("invalid topology format: %s, expected 3 dimensions", tpuTopology)
	}

	dims := make([]int64, 3)

	for i, dim := range dimensions {
		parsedDim, err := strconv.ParseInt(dim, 10, 32)
		if err != nil {
			return nil, TopologyTypeInvalid, err
		}
		dims[i] = parsedDim
	}

	if (dims[0] == 2 && dims[1] == 2 && dims[2] == 1) ||
		(dims[0] == 2 && dims[1] == 2 && dims[2] == 2) ||
		(dims[0] == 2 && dims[1] == 2 && dims[2] == 4) ||
		(dims[0] == 2 && dims[1] == 4 && dims[2] == 4) {
		return dims, TopologyTypeSubslice, nil
	}

	if dims[0] == 0 || dims[1] == 0 || dims[2] == 0 {
		return nil, TopologyTypeInvalid, fmt.Errorf("topology dimensions cannot be zero: %s", tpuTopology)
	}
	if dims[0]%4 != 0 || dims[1]%4 != 0 || dims[2]%4 != 0 {
		return nil, TopologyTypeInvalid, fmt.Errorf("topology dimensions must be divisible by 4: %s", tpuTopology)
	}
	if dims[0] > dims[1] || dims[1] > dims[2] {
		return nil, TopologyTypeInvalid, fmt.Errorf("topology dimensions must be in non-decreasing order: %s", tpuTopology)
	}

	return dims, TopologyTypeSuperslice, nil
}

func GetPartitionIdLabel(nodes map[string]corev1.Node, spec corev1.PodTemplateSpec) string {
	topology := GetTPUTopology(spec)
	_, topologyType, err := ParseTopology(topology)
	if err != nil {
		return ""
	}
	switch topologyType {
	case TopologyTypeSuperslice:
		return TPUSubBlockLabel
	case TopologyTypeSubslice:
		return fmt.Sprintf("cloud.google.com/gke-tpu-partition-%s-id", topology)
	}
	return ""
}
