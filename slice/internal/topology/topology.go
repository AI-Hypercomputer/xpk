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

package topology

import (
	"fmt"
	"strconv"
	"strings"
	"tpu-slice-controller/internal/core"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/util/sets"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta2"
	"sigs.k8s.io/kueue/pkg/util/tas"
)

// HostnameLevelIndex returns the index of the hostname level in the topology
// assignment, or -1 if it doesn't exist.
func HostnameLevelIndex(topologyAssignment *kueue.TopologyAssignment) int {
	for i, level := range topologyAssignment.Levels {
		if level == corev1.LabelHostname {
			return i
		}
	}
	return -1
}

type ParsedAssignment struct {
	PartitionIDs []string
}

func ParseAssignment(topologyAssignment *kueue.TopologyAssignment, nodes map[string]corev1.Node, labelKey string) ParsedAssignment {
	parsedAssignment := ParsedAssignment{
		PartitionIDs: make([]string, 0),
	}
	seenPartitionIDs := sets.New[string]()
	// we already validated that all assignments have a valid level,
	// in validateRelevantWorkload.
	hostnameLevelIndex := HostnameLevelIndex(topologyAssignment)
	for domain := range tas.InternalSeqFrom(topologyAssignment) {
		nodeName := domain.Values[hostnameLevelIndex]
		if partitionID := getTPUPartitionIDValue(nodes, nodeName, labelKey); !seenPartitionIDs.Has(partitionID) {
			parsedAssignment.PartitionIDs = append(parsedAssignment.PartitionIDs, partitionID)
			seenPartitionIDs.Insert(partitionID)
		}
	}
	return parsedAssignment
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
	topology := core.GetTPUTopology(spec)
	_, topologyType, err := ParseTopology(topology)
	if err != nil {
		return ""
	}
	switch topologyType {
	case TopologyTypeSuperslice:
		return core.TPUSubBlockLabel
	case TopologyTypeSubslice:
		return core.SubsliceLevelLabel(topology)
	}
	return ""
}
