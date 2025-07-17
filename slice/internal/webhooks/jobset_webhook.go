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
	kueuealpha "sigs.k8s.io/kueue/apis/kueue/v1alpha1"
	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"
)

const (
	TPUTopologyAnnotation = "cloud.google.com/gke-tpu-topology"
	TPUAcceleratorLabel   = "cloud.google.com/gke-tpu-accelerator"
	TPUBlockAnnotation    = "cloud.google.com/gke-tpu-block"
	TPUSubBlockAnnotation = "cloud.google.com/gke-tpu-subblock"
)

var (
	errInvalidTPUTopologyAnnotation = fmt.Errorf("invalid %s annotation", TPUTopologyAnnotation)
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
	log.V(5).Info("Applying defaults")

	if jobSet.Labels[kueueconstants.QueueLabel] == "" {
		return nil
	}

	for i, rj := range jobSet.Spec.ReplicatedJobs {
		tpuTopology := rj.Template.Spec.Template.Annotations[TPUTopologyAnnotation]
		tpuAccelerator := rj.Template.Spec.Template.Spec.NodeSelector[TPUAcceleratorLabel]

		if tpuTopology == "" || tpuAccelerator == "" {
			continue
		}

		if rj.Template.Annotations == nil {
			rj.Template.Annotations = make(map[string]string)
		}

		rj.Template.Annotations[kueuealpha.PodSetRequiredTopologyAnnotation] = rj.Template.Spec.Template.Annotations[TPUBlockAnnotation]
		rj.Template.Annotations[kueuealpha.PodSetSliceRequiredTopologyAnnotation] = rj.Template.Spec.Template.Annotations[TPUSubBlockAnnotation]

		size, err := podSetSliceSize(tpuTopology, ptr.Deref(rj.Template.Spec.Parallelism, 1))
		if err != nil {
			return err
		}
		rj.Template.Annotations[kueuealpha.PodSetSliceSizeAnnotation] = fmt.Sprint(size)

		jobSet.Spec.ReplicatedJobs[i] = rj
	}

	return nil
}

func podSetSliceSize(tpuTopology string, parallelism int32) (int32, error) {
	dimensions := strings.Split(tpuTopology, "x")
	if len(dimensions) < 2 || len(dimensions) > 3 {
		return 0, fmt.Errorf("%w: invalid dimension count in %q", errInvalidTPUTopologyAnnotation, tpuTopology)
	}

	subBlockCount := int32(1)
	for _, dim := range dimensions {
		if dim == "" {
			return 0, fmt.Errorf("%w: empty dimension in %q", errInvalidTPUTopologyAnnotation, tpuTopology)
		}

		partInt, err := strconv.ParseInt(dim, 10, 32)
		if err != nil {
			return 0, fmt.Errorf("%w: failed to parse dimension %q: %v", errInvalidTPUTopologyAnnotation, dim, err)
		}
		subBlockCount *= int32(partInt)
	}

	return parallelism / (subBlockCount / 64), nil
}
