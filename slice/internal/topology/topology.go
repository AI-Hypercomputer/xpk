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
	corev1 "k8s.io/api/core/v1"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	"tpu-slice-controller/internal/core"
)

func levelIndex(topologyAssignment *kueue.TopologyAssignment, level string) int {
	for i, currentLevel := range topologyAssignment.Levels {
		if level == currentLevel {
			return i
		}
	}
	return -1
}

// HostnameLevelIndex returns the index of the hostname level in the topology assignment, or -1 if none exists.
func HostnameLevelIndex(topologyAssignment *kueue.TopologyAssignment) int {
	return levelIndex(topologyAssignment, corev1.LabelHostname)
}

// SubblockLevelIndex returns the index of the subblock level in the topology assignment, or -1 if none exists.
func SubblockLevelIndex(topologyAssignment *kueue.TopologyAssignment) int {
	return levelIndex(topologyAssignment, core.TPUSubBlockLabel)
}
