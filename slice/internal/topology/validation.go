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

import kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

// AnyAssignment returns true if there exists
// at least 1 podset with a topology assignment.
func AnyAssignment(admission *kueue.Admission) bool {
	for _, psa := range admission.PodSetAssignments {
		if psa.TopologyAssignment != nil {
			return true
		}
	}
	return false
}

// AllAssignmentsValid ensures each PodSetAssignment which has a TopologyAssignment
// defined the TPUSubBlock topology level.
func AllAssignmentsValid(admission *kueue.Admission) bool {
	for _, psa := range admission.PodSetAssignments {
		if psa.TopologyAssignment == nil {
			continue
		}
		if SubblockLevelIndex(&psa) == -1 {
			return false
		}
	}
	return true
}
