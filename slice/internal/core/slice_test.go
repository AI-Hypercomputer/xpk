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

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta2"

	"tpu-slice-controller/api/v1beta1"
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

func TestFindExistingSlice(t *testing.T) {
	ns := "ns"
	wlName := "very-long-workload-name-exceeding-the-limit-for-testing"
	podSet := kueue.PodSetReference("ps")
	var index int32 = 0

	longName := SliceNameWithMaxLen(ns, wlName, podSet, index, maxSliceNameLength)
	shortName := SliceNameWithMaxLen(ns, wlName, podSet, index, maxShorterSliceNameLength)

	testCases := map[string]struct {
		gateEnabled bool
		m           map[string]*v1beta1.Slice
		wantFound   bool
		wantSlice   string
	}{
		"gate disabled, found long name": {
			gateEnabled: false,
			m: map[string]*v1beta1.Slice{
				longName: {ObjectMeta: metav1.ObjectMeta{Name: longName}},
			},
			wantFound: true,
			wantSlice: longName,
		},
		"gate enabled, found short name": {
			gateEnabled: true,
			m: map[string]*v1beta1.Slice{
				shortName: {ObjectMeta: metav1.ObjectMeta{Name: shortName}},
			},
			wantFound: true,
			wantSlice: shortName,
		},
		"gate enabled, found long name (fallback)": {
			gateEnabled: true,
			m: map[string]*v1beta1.Slice{
				longName: {ObjectMeta: metav1.ObjectMeta{Name: longName}},
			},
			wantFound: true,
			wantSlice: longName,
		},
		"gate enabled, not found": {
			gateEnabled: true,
			m:           map[string]*v1beta1.Slice{},
			wantFound:   false,
		},
	}

	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			features.SetFeatureGateDuringTest(t, features.ShorterSliceNameLength, tc.gateEnabled)
			got, found := FindExistingSlice(tc.m, ns, wlName, podSet, index)
			if found != tc.wantFound {
				t.Errorf("FindExistingSlice() found = %v, want %v", found, tc.wantFound)
			}
			if tc.wantFound && got.Name != tc.wantSlice {
				t.Errorf("FindExistingSlice() got name = %q, want %q", got.Name, tc.wantSlice)
			}
		})
	}
}
