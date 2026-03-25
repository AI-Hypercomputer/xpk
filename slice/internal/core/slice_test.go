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

	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta2"

	"tpu-slice-controller/internal/features"
)

func TestSliceName(t *testing.T) {
	testCases := map[string]struct {
		ns           string
		workloadName string
		podSetName   kueue.PodSetReference
		sliceIndex   int32
		want         string
		wantShorter  string
	}{
		"short name": {
			ns:           "default",
			workloadName: "wl",
			podSetName:   "main",
			sliceIndex:   0,
			want:         "default-wl-main-0",
		},
		"exact limit (54 chars)": {
			ns:           "ns",
			workloadName: "1234567890123456789012345678901234567890123456",
			podSetName:   "ps",
			sliceIndex:   0,
			want:         "ns-1234567890123456789012345678901234567890123456-ps-0",
			wantShorter:  "ns-1234567890123456789012345678901234567890-ef47a",
		},
		"long name": {
			ns:           "very-long-namespace-name",
			workloadName: "very-long-workload-name-that-exceeds-the-limit",
			podSetName:   "podset",
			sliceIndex:   0,
			want:         "very-long-namespace-name-very-long-workload-name-209e4",
			wantShorter:  "very-long-namespace-name-very-long-workload-209e4",
		},
		"long name, different podset": {
			ns:           "very-long-namespace-name",
			workloadName: "very-long-workload-name-that-exceeds-the-limit",
			podSetName:   "another-podset",
			sliceIndex:   0,
			want:         "very-long-namespace-name-very-long-workload-name-a06b5",
			wantShorter:  "very-long-namespace-name-very-long-workload-a06b5",
		},
		"long name, next index": {
			ns:           "very-long-namespace-name",
			workloadName: "very-long-workload-name-that-exceeds-the-limit",
			podSetName:   "podset",
			sliceIndex:   1,
			want:         "very-long-namespace-name-very-long-workload-name-36522",
			wantShorter:  "very-long-namespace-name-very-long-workload-36522",
		},
	}

	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			// Test with feature gate disabled (default)
			features.SetFeatureGateDuringTest(t, features.ShorterSliceNameLength, false)
			got := SliceName(tc.ns, tc.workloadName, tc.podSetName, tc.sliceIndex)
			if got != tc.want {
				t.Errorf("SliceName() [ShorterSliceNameLength disabled] = %q, want %q", got, tc.want)
			}

			// Test with feature gate enabled
			features.SetFeatureGateDuringTest(t, features.ShorterSliceNameLength, true)
			gotShorter := SliceName(tc.ns, tc.workloadName, tc.podSetName, tc.sliceIndex)
			expectedShorter := tc.want
			if tc.wantShorter != "" {
				expectedShorter = tc.wantShorter
			}
			if gotShorter != expectedShorter {
				t.Errorf("SliceName() [ShorterSliceNameLength enabled] = %q, want %q", gotShorter, expectedShorter)
			}
		})
	}
}
