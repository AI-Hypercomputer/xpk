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

package webhooks

import (
	"fmt"
	"strconv"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/utils/ptr"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/topology"
)

func getTPUsRequestedPerPod(spec corev1.PodSpec) int64 {
	var totalTPUs int64
	for _, container := range spec.Containers {
		if tpuQuantity, ok := container.Resources.Limits[core.TPUResourceName]; ok {
			totalTPUs += tpuQuantity.Value()
		}
	}
	return totalTPUs
}

func annotatePodTemplateSpecWithSliceHealth(template *corev1.PodTemplateSpec, defaultSliceHealthValues []string) {
	// 1. If there is NodeSelector with TPUSliceHealthNodeSelectorKey, we do nothing.
	if _, ok := template.Spec.NodeSelector[core.TPUSliceHealthNodeSelectorKey]; ok {
		return
	}

	// 2. If there is NodeAffinity with TPUSliceHealthNodeSelectorKey, we do nothing.
	if core.FindNodeAffinityRequirement(template, core.TPUSliceHealthNodeSelectorKey) != nil {
		return
	}

	// 3. If neither of these, we add a NodeAffinity.
	core.AddNodeAffinity(template, core.TPUSliceHealthNodeSelectorKey, corev1.NodeSelectorOpIn, defaultSliceHealthValues)
}

func annotatePodTemplateSpecWithTopology(template *corev1.PodTemplateSpec, parallelism *int32, resourceName string, resourceKind string) error {
	if template.Annotations == nil {
		template.Annotations = make(map[string]string)
	}

	template.Annotations[kueue.PodSetRequiredTopologyAnnotation] = core.TPUBlockLabel
	template.Annotations[kueue.PodSetSliceRequiredTopologyAnnotation] = core.TPUSubBlockLabel

	pods := ptr.Deref(parallelism, 1)

	sliceSize, err := topology.CalculateSliceSize(
		template.Annotations[core.TPUSliceTopologyAnnotation],
		pods,
	)
	if err != nil {
		return err
	}
	tpusRequestedPerPod := getTPUsRequestedPerPod(template.Spec)
	tpusRequestedPerCube := tpusRequestedPerPod * sliceSize
	if tpusRequestedPerCube != core.TPUsPerCube {
		return fmt.Errorf("invalid %s %q: configuration results in %d TPUs requested per cube, but must be exactly %d TPUs (full utilization)", resourceKind, resourceName, tpusRequestedPerCube, core.TPUsPerCube)
	}

	template.Annotations[kueue.PodSetSliceSizeAnnotation] = strconv.FormatInt(sliceSize, 10)
	return nil
}

func addNodeInSliceAntiAffinity(template *corev1.PodTemplateSpec) {
	if req := core.FindNodeAffinityRequirement(template, core.TPUSliceNodeLabel); req != nil && req.Operator == corev1.NodeSelectorOpDoesNotExist {
		return
	}
	core.AddNodeAffinity(template, core.TPUSliceNodeLabel, corev1.NodeSelectorOpDoesNotExist, nil)
}

func removeNodeInSliceAntiAffinity(spec *corev1.PodSpec) {
	if spec.Affinity == nil ||
		spec.Affinity.NodeAffinity == nil ||
		spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution == nil {
		return
	}

	nodeSelector := spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution
	for i := range nodeSelector.NodeSelectorTerms {
		var newExpressions []corev1.NodeSelectorRequirement
		for _, req := range nodeSelector.NodeSelectorTerms[i].MatchExpressions {
			if req.Key != core.TPUSliceNodeLabel || req.Operator != corev1.NodeSelectorOpDoesNotExist {
				newExpressions = append(newExpressions, req)
			}
		}
		nodeSelector.NodeSelectorTerms[i].MatchExpressions = newExpressions
	}
}
