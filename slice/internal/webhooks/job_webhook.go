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

	batchv1 "k8s.io/api/batch/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/webhook"
	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"

	"tpu-slice-controller/internal/core"
)

type JobWebhook struct {
	DefaultSliceHealthValues []string
}

func SetupJobWebhookWithManager(mgr ctrl.Manager, defaultSliceHealthValues []string) error {
	return ctrl.NewWebhookManagedBy(mgr).
		For(&batchv1.Job{}).
		WithDefaulter(&JobWebhook{
			DefaultSliceHealthValues: defaultSliceHealthValues,
		}).
		Complete()
}

// +kubebuilder:webhook:path=/mutate-batch-v1-job,mutating=true,failurePolicy=fail,sideEffects=None,groups=batch,resources=jobs,verbs=create,versions=v1,name=mjob.kb.io,admissionReviewVersions=v1

var _ webhook.CustomDefaulter = &JobWebhook{}

func (r *JobWebhook) Default(ctx context.Context, obj runtime.Object) error {
	job := obj.(*batchv1.Job)
	log := ctrl.LoggerFrom(ctx).WithName("job-accelerator-gke-webhook")
	log.V(5).Info("Defaulting Job")

	if job.Labels[kueueconstants.QueueLabel] == "" {
		log.V(5).Info("Skipping due to missing Kueue Label")
		return nil
	}

	if !core.IsRelevantPodTemplateSpec(job.Spec.Template) {
		log.V(5).Info("Skipping annotating Job due to TPU Annotation or Node Selector misconfigured")
		return nil
	}
	log.V(5).Info("Annotating Job")
	annotatePodTemplateSpecWithSliceHealth(&job.Spec.Template, r.DefaultSliceHealthValues)
	err := annotatePodTemplateSpecWithTopology(&job.Spec.Template, job.Spec.Parallelism, job.Name, "job")
	if err != nil {
		return err
	}

	return nil
}
