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
	"slices"
	"strconv"
	"strings"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/util/sets"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta2"
	"sigs.k8s.io/kueue/pkg/util/tas"

	"tpu-slice-controller/internal/core"
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

type TopologyType string

const (
	TopologyTypeSuperslice TopologyType = "Superslice"
	TopologyTypeSubslice   TopologyType = "Subslice"
)

type ParsedTopology interface {
	Dims() []int64
	Type() TopologyType
	RequiredSliceLevel() string
	HealthLabel() string
	NumberOfTPUsPerSlice() int64
	DesiredNumberOfPartitions() int64
	SliceSize(parallelism int32) int64
}

var SupportedSubsliceTopologies = sets.New("2x2x1", "2x2x2", "2x2x4", "2x4x4")

func ParseTopologyV7(tpuTopology string) (ParsedTopology, error) {
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

	if SupportedSubsliceTopologies.Has(tpuTopology) {
		return subsliceTopology{dims: dims}, nil
	}

	if slices.Contains(dims, 0) {
		return nil, fmt.Errorf("topology dimensions cannot be zero: %s", tpuTopology)
	}
	if dims[0]%4 != 0 || dims[1]%4 != 0 || dims[2]%4 != 0 {
		return nil, fmt.Errorf("topology dimensions must be divisible by 4: %s", tpuTopology)
	}
	if dims[0] > dims[1] || dims[1] > dims[2] {
		return nil, fmt.Errorf("topology dimensions must be in non-decreasing order: %s", tpuTopology)
	}

	return supersliceTopology{dims: dims}, nil
}

func GetPartitionIDLabel(spec corev1.PodTemplateSpec) string {
	topology := core.GetTPUTopology(spec)
	parsed, err := ParseTopologyV7(topology)
	if err != nil {
		return ""
	}
	return parsed.RequiredSliceLevel()
}

type subsliceTopology struct {
	dims []int64
}

func (s subsliceTopology) Dims() []int64      { return s.dims }
func (s subsliceTopology) Type() TopologyType { return TopologyTypeSubslice }
func (s subsliceTopology) RequiredSliceLevel() string {
	return fmt.Sprintf("cloud.google.com/gke-tpu-partition-%dx%dx%d-id", s.dims[0], s.dims[1], s.dims[2])
}
func (s subsliceTopology) HealthLabel() string {
	return fmt.Sprintf("cloud.google.com/gke-tpu-partition-%dx%dx%d-state", s.dims[0], s.dims[1], s.dims[2])
}
func (s subsliceTopology) NumberOfTPUsPerSlice() int64 {
	return s.dims[0] * s.dims[1] * s.dims[2]
}
func (s subsliceTopology) DesiredNumberOfPartitions() int64 { return 1 }
func (s subsliceTopology) SliceSize(parallelism int32) int64 {
	return int64(parallelism)
}

type supersliceTopology struct {
	dims []int64
}

func (s supersliceTopology) Dims() []int64               { return s.dims }
func (s supersliceTopology) Type() TopologyType          { return TopologyTypeSuperslice }
func (s supersliceTopology) RequiredSliceLevel() string  { return core.TPUSubBlockLabel }
func (s supersliceTopology) HealthLabel() string         { return core.TPUSliceHealthNodeSelectorKey }
func (s supersliceTopology) NumberOfTPUsPerSlice() int64 { return core.TPUsPerCube }
func (s supersliceTopology) DesiredNumberOfPartitions() int64 {
	return s.dims[0] * s.dims[1] * s.dims[2] / core.TPUsPerCube
}
func (s supersliceTopology) SliceSize(parallelism int32) int64 {
	totalChips := s.dims[0] * s.dims[1] * s.dims[2]
	subBlockCount := totalChips / core.TPUsPerCube
	return int64(parallelism) / subBlockCount
}
