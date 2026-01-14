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
	"strings"
	"testing"

	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
)

func TestSliceName(t *testing.T) {
	testCases := map[string]struct {
		ns           string
		workloadName string
		podSetName   kueue.PodSetReference
		sliceIndex   int32
		want         string
	}{
		"short name": {
			ns:           "default",
			workloadName: "wl",
			podSetName:   "main",
			sliceIndex:   0,
			want:         "default-wl-main-0",
		},
		"exact limit (63 chars)": {
			ns:           "ns",
			workloadName: "1234567890123456789012345678901234567890123456789012345",
			podSetName:   "ps",
			sliceIndex:   0,
			want:         "ns-1234567890123456789012345678901234567890123456789012345-ps-0",
		},
		"long name": {
			ns:           "very-long-namespace-name",
			workloadName: "very-long-workload-name-that-exceeds-the-limit",
			podSetName:   "podset",
			sliceIndex:   0,
			want:         "very-long-namespace-name-very-long-workload-name-tha-209e4f3863",
		},
		"long name, next index": {
			ns:           "very-long-namespace-name",
			workloadName: "very-long-workload-name-that-exceeds-the-limit",
			podSetName:   "podset",
			sliceIndex:   1,
			want:         "very-long-namespace-name-very-long-workload-name-tha-365229f91c",
		},
	}

	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			got := SliceName(tc.ns, tc.workloadName, tc.podSetName, tc.sliceIndex)
			if len(got) > 63 {
				t.Errorf("SliceName() length = %d, want <= 63", len(got))
			}
			if tc.want != "" {
				if got != tc.want {
					t.Errorf("SliceName() = %q, want %q", got, tc.want)
				}
			} else {
				expectedPrefix := fmt.Sprintf("%s-%s-%s-%d", tc.ns, tc.workloadName, tc.podSetName, tc.sliceIndex)[:52]
				if !strings.HasPrefix(got, expectedPrefix) {
					t.Errorf("SliceName() prefix = %q, want %q", got[:52], expectedPrefix)
				}
			}
		})
	}
}
