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
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestParseTopology(t *testing.T) {
	testCases := map[string]struct {
		topology string
		wantDims []int64
		wantType TopologyType
		wantErr  bool
	}{
		"valid 4x4x4": {
			topology: "4x4x4",
			wantDims: []int64{4, 4, 4},
			wantType: TopologyTypeSuperslice,
			wantErr:  false,
		},
		"valid 4x4x8": {
			topology: "4x4x8",
			wantDims: []int64{4, 4, 8},
			wantType: TopologyTypeSuperslice,
			wantErr:  false,
		},
		"valid max 16x24x24": {
			topology: "16x24x24",
			wantDims: []int64{16, 24, 24},
			wantType: TopologyTypeSuperslice,
			wantErr:  false,
		},
		"valid subslice 2x2x1": {
			topology: "2x2x1",
			wantDims: []int64{2, 2, 1},
			wantType: TopologyTypeSubslice,
			wantErr:  false,
		},
		"valid subslice 2x2x2": {
			topology: "2x2x2",
			wantDims: []int64{2, 2, 2},
			wantType: TopologyTypeSubslice,
			wantErr:  false,
		},
		"valid subslice 2x2x4": {
			topology: "2x2x4",
			wantDims: []int64{2, 2, 4},
			wantType: TopologyTypeSubslice,
			wantErr:  false,
		},
		"valid subslice 2x4x4": {
			topology: "2x4x4",
			wantDims: []int64{2, 4, 4},
			wantType: TopologyTypeSubslice,
			wantErr:  false,
		},
		"invalid format (2 dims)": {
			topology: "4x4",
			wantType: TopologyTypeInvalid,
			wantErr:  true,
		},
		"invalid format (4 dims)": {
			topology: "4x4x4x4",
			wantType: TopologyTypeInvalid,
			wantErr:  true,
		},
		"invalid format (non-int)": {
			topology: "4x4xa",
			wantType: TopologyTypeInvalid,
			wantErr:  true,
		},
		"not divisible by 4": {
			topology: "3x4x4",
			wantType: TopologyTypeInvalid,
			wantErr:  true,
		},
		"not non-decreasing": {
			topology: "8x4x4",
			wantType: TopologyTypeInvalid,
			wantErr:  true,
		},
		"exceeds max": {
			topology: "20x24x24",
			wantType: TopologyTypeInvalid,
			wantErr:  true,
		},
		"zero dimension": {
			topology: "0x4x4",
			wantType: TopologyTypeInvalid,
			wantErr:  true,
		},
		"unparseable": {
			topology: "4x4x4x",
			wantType: TopologyTypeInvalid,
			wantErr:  true,
		},
		"incomplete": {
			topology: "4x4x",
			wantType: TopologyTypeInvalid,
			wantErr:  true,
		},
	}

	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			dims, topoType, err := ParseTopology(tc.topology)
			if (err != nil) != tc.wantErr {
				t.Errorf("parseTopology() error = %v, wantErr %v", err, tc.wantErr)
				return
			}
			if !tc.wantErr {
				if diff := cmp.Diff(tc.wantDims, dims); diff != "" {
					t.Errorf("parseTopology() mismatch (-want +got):\n%s", diff)
				}
				if topoType != tc.wantType {
					t.Errorf("parseTopology() type = %v, want %v", topoType, tc.wantType)
				}
			}
		})
	}
}
