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

package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// NOTE: json tags are required.  Any new fields you add must have json tags for the fields to be serialized.

// SliceSpec defines the desired state of Slice.
type SliceSpec struct {
	// AcceleratorType specifies the type of accelerator used in this slice.
	// +kubebuilder:validation:Immutable
	AcceleratorType string `json:"acceleratorType"`

	// Topology represents the network topology of the slice.
	// +kubebuilder:validation:Immutable
	AcceleratorTopology string `json:"acceleratorTopology"`

	// Required, set of nodes to use to form a slice.
	// NodeSelector specifies a set of label-based selectors for nodes that can form the
	// slice. The controller will select nodes where for each key-value pair in the map,
	// the node's label value for that key is present in the corresponding string slice.
	// This allows for a flexible "match any of these values for this label" selection.
	// The nodeSelector will follow an AND over the map entries but an OR within the list
	// items of the entry.
	// For example, to select nodes in cubes cube-1 and cube-2, you could use:
	// {"cloud.google.com/gke-tpu-reservation-subblock": ["cube-1", "cube-2"]}
	//
	// +kubebuilder:validation:Required
	NodeSelector map[string][]string `json:"nodeSelector"`
}

// SliceStatus defines the observed state of Slice.
type SliceStatus struct {
	// Conditions store the status conditions of the Slice
	// +operator-sdk:csv:customresourcedefinitions:type=status
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// Populated to match the physical topology of block the Super-Slice is running on
	BlockID string `json:"blockId,omitempty"`

	// Populated to list of physical topology of sub-block the Super-Slice is running on
	SubBlockIDs []string `json:"subBlockIds,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:printcolumn:name="Type",type=string,JSONPath=`.spec.acceleratorType`
// +kubebuilder:printcolumn:name="Topology",type=string,JSONPath=`.spec.acceleratorTopology`
// +kubebuilder:printcolumn:name="Status",type=string,JSONPath=`.status.conditions[0].type`
// +kubebuilder:printcolumn:name="Age",type="date",JSONPath=".metadata.creationTimestamp"
// Slice is the Schema for the slices API.
type Slice struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   SliceSpec   `json:"spec,omitempty"`
	Status SliceStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// SliceList contains a list of Slice.
type SliceList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []Slice `json:"items"`
}

// SliceConditionType defines the type of condition
type SliceConditionType string

const (
	// Forming means the slice is being created and configured.
	Forming SliceConditionType = "Forming"
	// Ready means the slice is fully operational.
	Ready SliceConditionType = "Ready"
	// Degraded means the slice is operational but with reduced capacity or performance.
	Degraded SliceConditionType = "Degraded"
	// Deformed means the slice is being torn down.
	Deformed SliceConditionType = "Deformed"
	// Error means the slice has encountered an error and is not operational.
	Error SliceConditionType = "Error"
)

func init() {
	SchemeBuilder.Register(&Slice{}, &SliceList{})
}
