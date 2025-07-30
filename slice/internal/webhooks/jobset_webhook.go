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
	"strconv"
	"strings"

	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/utils/ptr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/webhook"
	"sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueuealpha "sigs.k8s.io/kueue/apis/kueue/v1alpha1"
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
	log.V(5).Info("Applying defaults")

	if jobSet.Labels[kueueconstants.QueueLabel] == "" {
		return nil
	}

	for i := range jobSet.Spec.ReplicatedJobs {
		err := r.annotateReplicatedJobWithTopology(&jobSet.Spec.ReplicatedJobs[i])
		if err != nil {
			return err
		}
	}

	return nil
}

func (r *JobSetWebhook) annotateReplicatedJobWithTopology(rj *v1alpha2.ReplicatedJob) error {
	if !core.IsRelevantPodTemplateSpec(rj.Template.Spec.Template) {
		return nil
	}

	if rj.Template.Spec.Template.Annotations == nil {
		rj.Template.Spec.Template.Annotations = make(map[string]string)
	}

	rj.Template.Spec.Template.Annotations[kueuealpha.PodSetRequiredTopologyAnnotation] = core.TPUBlockLabel
	rj.Template.Spec.Template.Annotations[kueuealpha.PodSetSliceRequiredTopologyAnnotation] = core.TPUSubBlockLabel

	pods := ptr.Deref(rj.Template.Spec.Parallelism, 1) * rj.Replicas

	size, err := r.podSetSliceSize(
		rj.Template.Spec.Template.Annotations[core.TPUTopologyAnnotation],
		pods,
	)
	if err != nil {
		return err
	}
	rj.Template.Spec.Template.Annotations[kueuealpha.PodSetSliceSizeAnnotation] = size

	return nil
}

func (r *JobSetWebhook) podSetSliceSize(tpuTopology string, parallelism int32) (string, error) {
	dimensions := strings.Split(tpuTopology, "x")
	totalChips := int64(1)

	for _, dim := range dimensions {
		parsedDim, err := strconv.ParseInt(dim, 10, 8)
		if err != nil {
			return "", err
		}
		totalChips *= parsedDim
	}

	subBlockCount := totalChips / 64

	return strconv.FormatInt(int64(parallelism)/subBlockCount, 10), nil
}
