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
	"errors"
	"fmt"
	"strconv"

	corev1 "k8s.io/api/core/v1"
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

func annotatePodTemplateSpecWithSliceHealth(template *corev1.PodTemplateSpec, parsedTopology topology.ParsedTopology, defaultSliceHealthValues []string) {
	healthLabel := parsedTopology.HealthLabel()

	// 1. If there is NodeSelector with healthLabel, we do nothing.
	if _, ok := template.Spec.NodeSelector[healthLabel]; ok {
		return
	}

	// 2. If there is NodeAffinity with healthLabel, we do nothing.
	if template.Spec.Affinity != nil &&
		template.Spec.Affinity.NodeAffinity != nil &&
		template.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution != nil {
		for _, term := range template.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms {
			for _, req := range term.MatchExpressions {
				if req.Key == healthLabel {
					return
				}
			}
		}
	}

	// 3. If neither of these, we add a NodeAffinity.
	core.AddNodeAffinity(template, healthLabel, defaultSliceHealthValues)
}

func annotatePodTemplateSpecWithTopology(template *corev1.PodTemplateSpec, parsedTopology topology.ParsedTopology, parallelism *int32) error {
	if template.Annotations == nil {
		template.Annotations = make(map[string]string)
	}
	if parallelism == nil {
		return errors.New("parallelism must be set for Sub-/SuperSlice workloads")
	}
	pods := *parallelism
	tpusRequestedPerPod := getTPUsRequestedPerPod(template.Spec)
	sliceSize := parsedTopology.SliceSize(pods)
	numberOfTPUsPerSlice := parsedTopology.NumberOfTPUsPerSlice()
	// the number of TPUs specified in topology annotation
	// must match the number of TPUs requested by the pods
	if tpusRequestedPerPod*sliceSize != numberOfTPUsPerSlice {
		return fmt.Errorf("configuration results in %d TPUs requested, but must be exactly %d TPUs (full utilization)", tpusRequestedPerPod*sliceSize, numberOfTPUsPerSlice)
	}
	template.Annotations[kueue.PodSetRequiredTopologyAnnotation] = core.TPUBlockLabel
	template.Annotations[kueue.PodSetSliceRequiredTopologyAnnotation] = parsedTopology.RequiredSliceLevel()
	template.Annotations[kueue.PodSetSliceSizeAnnotation] = strconv.FormatInt(sliceSize, 10)
	return nil
}
