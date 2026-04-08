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

	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/webhook/admission"
	"sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"

	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/topology"
)

// JobSetWebhook is the schema for your resource (ensure this matches your resource definition).
type JobSetWebhook struct {
	DefaultSliceHealthValues []string
}

func SetupWebhookWithManager(mgr ctrl.Manager, defaultSliceHealthValues []string) error {
	return ctrl.NewWebhookManagedBy(mgr, &v1alpha2.JobSet{}).
		WithDefaulter(&JobSetWebhook{
			DefaultSliceHealthValues: defaultSliceHealthValues,
		}).
		Complete()
}

// +kubebuilder:webhook:path=/mutate-jobset-x-k8s-io-v1alpha2-jobset,mutating=true,failurePolicy=fail,sideEffects=None,groups=jobset.x-k8s.io,resources=jobsets,verbs=create,versions=v1alpha2,name=mjobset.kb.io,admissionReviewVersions=v1

var _ admission.Defaulter[*v1alpha2.JobSet] = &JobSetWebhook{}

// Default implements admission.Defaulter so a webhook will be registered for the type
func (r *JobSetWebhook) Default(ctx context.Context, jobSet *v1alpha2.JobSet) error {
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
		tpuTopology := rj.Template.Spec.Template.Annotations[core.TPUSliceTopologyAnnotation]
		parsed, err := topology.ParseTopologyV7(tpuTopology)
		if err != nil {
			return err
		}
		annotatePodTemplateSpecWithSliceHealth(&rj.Template.Spec.Template, parsed, r.DefaultSliceHealthValues)
		err = annotatePodTemplateSpecWithTopology(&rj.Template.Spec.Template, parsed, rj.Template.Spec.Parallelism)
		if err != nil {
			return fmt.Errorf("invalid jobset %q: %w", jobSet.Name, err)
		}
	}

	return nil
}
