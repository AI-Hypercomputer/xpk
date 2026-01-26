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
	"context"
	"fmt"
	"strconv"
	"strings"

	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/utils/ptr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/webhook"
	"sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"

	"tpu-slice-controller/internal/core"
)

// JobSetWebhook is the schema for your resource (ensure this matches your resource definition).
type JobSetWebhook struct{}

func SetupWebhookWithManager(mgr ctrl.Manager) error {
	return ctrl.NewWebhookManagedBy(mgr).
		For(&v1alpha2.JobSet{}).
		WithDefaulter(&JobSetWebhook{}).
		Complete()
}

// +kubebuilder:webhook:path=/mutate-jobset-x-k8s-io-v1alpha2-jobset,mutating=true,failurePolicy=fail,sideEffects=None,groups=jobset.x-k8s.io,resources=jobsets,verbs=create,versions=v1alpha2,name=mjobset.kb.io,admissionReviewVersions=v1
var _ webhook.CustomDefaulter = &JobSetWebhook{}

// Default implements webhook.CustomDefaulter so a webhook will be registered for the type
func (r *JobSetWebhook) Default(ctx context.Context, obj runtime.Object) error {
	jobSet := obj.(*v1alpha2.JobSet)
	log := ctrl.LoggerFrom(ctx).WithName("jobset-accelerator-gke-webhook")
	log.V(5).Info("Defaulting JobSet")

	if jobSet.Labels[kueueconstants.QueueLabel] == "" {
		log.V(5).Info("Skipping due to missing Kueue Label")
		return nil
	}

	for i := range jobSet.Spec.ReplicatedJobs {
		rj := &jobSet.Spec.ReplicatedJobs[i]
		if !core.IsRelevantPodTemplateSpec(rj.Template.Spec.Template) {
			log.V(5).Info("Skipping annotating ReplicatedJob due to TPU Annotation or Node Selector misconfigured")
			continue
		}
		log.V(5).Info("Annotating ReplicatedJob")
		annotateReplicatedJobWithSliceHealth(rj)
		err := r.annotateReplicatedJobWithTopology(rj)
		if err != nil {
			return err
		}
	}

	return nil
}

func (r *JobSetWebhook) annotateReplicatedJobWithTopology(rj *v1alpha2.ReplicatedJob) error {
	if rj.Template.Spec.Template.Annotations == nil {
		rj.Template.Spec.Template.Annotations = make(map[string]string)
	}

	rj.Template.Spec.Template.Annotations[kueue.PodSetRequiredTopologyAnnotation] = core.TPUBlockLabel
	rj.Template.Spec.Template.Annotations[kueue.PodSetSliceRequiredTopologyAnnotation] = core.TPUSubBlockLabel

	pods := ptr.Deref(rj.Template.Spec.Parallelism, 1)

	sliceSize, err := r.podSetSliceSize(
		rj.Template.Spec.Template.Annotations[core.TPUSliceTopologyAnnotation],
		pods,
	)
	if err != nil {
		return err
	}
	tpuRequestedPerPod := r.getTPURequestedPerPod(rj)
	tpuRequestedPerCube := tpuRequestedPerPod * sliceSize
	if tpuRequestedPerCube != core.TPUsPerCube {
		return fmt.Errorf("invalid replicated job %q: configuration results in %d TPUs requested per cube, but must be exactly %d TPUs (full utilization)", rj.Name, tpuRequestedPerCube, core.TPUsPerCube)
	}

	rj.Template.Spec.Template.Annotations[kueue.PodSetSliceSizeAnnotation] = strconv.FormatInt(sliceSize, 10)
	return nil
}

func (r *JobSetWebhook) getTPURequestedPerPod(rj *v1alpha2.ReplicatedJob) int64 {
	var totalTPUs int64
	for _, container := range rj.Template.Spec.Template.Spec.Containers {
		if tpuQuantity, ok := container.Resources.Limits[core.TPUResourceName]; ok {
			totalTPUs += tpuQuantity.Value()
		}
	}
	return totalTPUs
}

func annotateReplicatedJobWithSliceHealth(rj *v1alpha2.ReplicatedJob) {
	// 1. If there is NodeSelector with TPUSliceHealthNodeSelectorKey, we do nothing.
	if _, ok := rj.Template.Spec.Template.Spec.NodeSelector[core.TPUSliceHealthNodeSelectorKey]; ok {
		return
	}

	// 2. If there is NodeAffinity with TPUSliceHealthNodeSelectorKey, we do nothing.
	if rj.Template.Spec.Template.Spec.Affinity != nil &&
		rj.Template.Spec.Template.Spec.Affinity.NodeAffinity != nil &&
		rj.Template.Spec.Template.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution != nil {
		for _, term := range rj.Template.Spec.Template.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms {
			for _, req := range term.MatchExpressions {
				if req.Key == core.TPUSliceHealthNodeSelectorKey {
					return
				}
			}
		}
	}

	// 3. If neither of these, we add a NodeAffinity.
	core.AddNodeAffinity(rj, core.TPUSliceHealthNodeSelectorKey, []string{core.TPUSliceHealthNodeSelectorHealthy, core.TPUSliceHealthNodeSelectorDegraded})
}

func (r *JobSetWebhook) podSetSliceSize(tpuTopology string, parallelism int32) (int64, error) {
	dims, err := parseTopology(tpuTopology)
	if err != nil {
		return 0, err
	}

	totalChips := dims[0] * dims[1] * dims[2]
	subBlockCount := totalChips / 64

	return int64(parallelism) / subBlockCount, nil
}

func parseTopology(tpuTopology string) ([]int64, error) {
	dimensions := strings.Split(tpuTopology, "x")
	if len(dimensions) != 3 {
		return nil, fmt.Errorf("invalid topology format: %s, expected 3 dimensions", tpuTopology)
	}

	dims := make([]int64, 3)

	for i, dim := range dimensions {
		parsedDim, err := strconv.ParseInt(dim, 10, 32)
		if err != nil {
			return nil, err
		}
		dims[i] = parsedDim
	}
	if dims[0] == 0 || dims[1] == 0 || dims[2] == 0 {
		return nil, fmt.Errorf("topology dimensions cannot be zero: %s", tpuTopology)
	}
	if dims[0]%4 != 0 || dims[1]%4 != 0 || dims[2]%4 != 0 {
		return nil, fmt.Errorf("topology dimensions must be divisible by 4: %s", tpuTopology)
	}
	if dims[0] > dims[1] || dims[1] > dims[2] {
		return nil, fmt.Errorf("topology dimensions must be in non-decreasing order: %s", tpuTopology)
	}
	if dims[0] > 16 || dims[1] > 24 || dims[2] > 24 {
		return nil, fmt.Errorf("topology dimensions exceed maximum 16x24x24: %s", tpuTopology)
	}

	return dims, nil
}
