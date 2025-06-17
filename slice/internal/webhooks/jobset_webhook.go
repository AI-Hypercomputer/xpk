/*
Copyright 2025.

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

	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/webhook"
	"sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"
)

const (
	PodSetRequiredTopologyAnnotation      = "kueue.x-k8s.io/podset-required-topology"
	PodSetSliceRequiredTopologyAnnotation = "kueue.x-k8s.io/podset-slice-required-topology"
	PodSetSliceSizeAnnotation             = "kueue.x-k8s.io/podset-slice-size"
)

const (
	annotationValueTBD = "TBD"
)

// JobSetWebhook is the schema for your resource (ensure this matches your resource definition).
type JobSetWebhook struct{}

func SetupWebhookWithManager(mgr ctrl.Manager) error {
	return ctrl.NewWebhookManagedBy(mgr).
		For(&v1alpha2.JobSet{}).
		WithDefaulter(&JobSetWebhook{}).
		Complete()
}

// +kubebuilder:webhook:path=/mutate-jobset-x-k8s-io-v1alpha2-jobset,mutating=true,failurePolicy=fail,sideEffects=None,groups=jobset.x-k8s.io,resources=jobsets,verbs=create,versions=v1alpha2,name=mjobset.accelerator.gke.io,admissionReviewVersions=v1
var _ webhook.CustomDefaulter = &JobSetWebhook{}

// Default implements webhook.CustomDefaulter so a webhook will be registered for the type
func (r *JobSetWebhook) Default(ctx context.Context, obj runtime.Object) error {
	jobSet := obj.(*v1alpha2.JobSet)
	log := ctrl.LoggerFrom(ctx).WithName("jobset-accelerator-gke-webhook")
	log.V(5).Info("Applying defaults")

	// handle webhooks for Kueue related JobSets
	cq, ok := jobSet.Labels[kueueconstants.QueueLabel]
	if !ok || cq == "" {
		return nil
	}

	for i, rj := range jobSet.Spec.ReplicatedJobs {
		if rj.Template.Annotations == nil {
			rj.Template.Annotations = make(map[string]string)
		}
		rj.Template.Annotations[PodSetRequiredTopologyAnnotation] = annotationValueTBD
		rj.Template.Annotations[PodSetSliceRequiredTopologyAnnotation] = annotationValueTBD
		rj.Template.Annotations[PodSetSliceSizeAnnotation] = annotationValueTBD

		jobSet.Spec.ReplicatedJobs[i] = rj
	}

	return nil
}
