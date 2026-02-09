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

func ParseAssignment(topologyAssignment *kueue.TopologyAssignment, nodes map[string]corev1.Node) ParsedAssignment {
	parsedAssignment := ParsedAssignment{
		PartitionIDs: make([]string, 0),
	}
	seenPartitionIDs := sets.New[string]()
	// we already validated that all assignments have a valid level,
	// in validateRelevantWorkload.
	hostnameLevelIndex := HostnameLevelIndex(topologyAssignment)
	for domain := range tas.InternalSeqFrom(topologyAssignment) {
		nodeName := domain.Values[hostnameLevelIndex]
		if partitionID := getTPUPartitionIDValue(nodes, nodeName); !seenPartitionIDs.Has(partitionID) {
			parsedAssignment.PartitionIDs = append(parsedAssignment.PartitionIDs, partitionID)
			seenPartitionIDs.Insert(partitionID)
		}
	}
	return parsedAssignment
}

func ParseTopology(tpuTopology string) ([]int64, error) {
	dimensions := strings.Split(tpuTopology, "x")
	if len(dimensions) != 3 {
		return nil, fmt.Errorf("invalid topology format: %s, expected 3 dimensions", tpuTopology)
	}

	dims := make([]int64, 3)

	for i, dim := range dimensions {
		parsedDim, err := strconv.ParseInt(dim, 10, 32)
		if err != nil {
			return nil, err
		}
		dims[i] = parsedDim
	}
	if dims[0] == 0 || dims[1] == 0 || dims[2] == 0 {
		return nil, fmt.Errorf("topology dimensions cannot be zero: %s", tpuTopology)
	}
	if dims[0]%4 != 0 || dims[1]%4 != 0 || dims[2]%4 != 0 {
		return nil, fmt.Errorf("topology dimensions must be divisible by 4: %s", tpuTopology)
	}
	if dims[0] > dims[1] || dims[1] > dims[2] {
		return nil, fmt.Errorf("topology dimensions must be in non-decreasing order: %s", tpuTopology)
	}
	if dims[0] > 16 || dims[1] > 24 || dims[2] > 24 {
		return nil, fmt.Errorf("topology dimensions exceed maximum 16x24x24: %s", tpuTopology)
	}

	return dims, nil
}
