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

type MMIGHealthStatus string

const (
	TPUTopologyAnnotation = "cloud.google.com/gke-tpu-topology"
	TPUAcceleratorLabel   = "cloud.google.com/gke-tpu-accelerator"
	TPUBlockLabel         = "cloud.google.com/gce-topology-block"
	TPUSubBlockLabel      = "cloud.google.com/gke-tpu-slice-4x4x4-id"

	TPUSliceHealthNodeSelectorKey   = "cloud.google.com/gke-tpu-slice-4x4x4-health"
	TPUSliceHealthNodeSelectorValue = "true"
)

const (
	// MMIGHealthStatusIncomplete indicates the MMIG is incomplete.
	MMIGHealthStatusIncomplete MMIGHealthStatus = "INCOMPLETE"
	// MMIGHealthStatusActivating indicates the MMIG is activating.
	MMIGHealthStatusActivating MMIGHealthStatus = "ACTIVATING"
	// MMIGHealthStatusActive indicates the MMIG is active.
	MMIGHealthStatusActive MMIGHealthStatus = "ACTIVE"
	// MMIGHealthStatusActiveDegraded indicates the MMIG is active but degraded.
	MMIGHealthStatusActiveDegraded MMIGHealthStatus = "ACTIVE_DEGRADED"
	// MMIGHealthStatusDeactivating indicates the MMIG is deactivating.
	MMIGHealthStatusDeactivating MMIGHealthStatus = "DEACTIVATING"
	// MMIGHealthStatusFailed indicates the MMIG has failed.
	MMIGHealthStatusFailed MMIGHealthStatus = "FAILED"
	// MMIGHealthStatusUnknown indicates the MMIG health is unknown.
	MMIGHealthStatusUnknown MMIGHealthStatus = "UNKNOWN"
)
