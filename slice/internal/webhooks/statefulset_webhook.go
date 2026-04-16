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

	appsv1 "k8s.io/api/apps/v1"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/webhook/admission"

	"tpu-slice-controller/internal/core"
)

type StatefulSetWebhook struct{}

func SetupStatefulSetWebhookWithManager(mgr ctrl.Manager) error {
	return ctrl.NewWebhookManagedBy(mgr, &appsv1.StatefulSet{}).
		WithDefaulter(&StatefulSetWebhook{}).
		Complete()
}

// +kubebuilder:webhook:path=/mutate-apps-v1-statefulset,mutating=true,failurePolicy=fail,sideEffects=None,groups=apps,resources=statefulsets,verbs=create,versions=v1,name=mstatefulset.slice-controller.kb.io,admissionReviewVersions=v1

var _ admission.Defaulter[*appsv1.StatefulSet] = &StatefulSetWebhook{}

func (r *StatefulSetWebhook) Default(ctx context.Context, sts *appsv1.StatefulSet) error {
	log := ctrl.LoggerFrom(ctx).WithName("statefulset-webhook")

	if !core.IsRelevantPodTemplateSpec(sts.Spec.Template) {
		log.V(5).Info("Skipping non-relevant StatefulSet")
		return nil
	}

	log.V(5).Info("Defaulting StatefulSet")
	tpuTopology := core.GetTPUTopology(sts.Spec.Template)
	if sts.Spec.Template.Spec.NodeSelector == nil {
		sts.Spec.Template.Spec.NodeSelector = make(map[string]string)
	}
	if _, ok := sts.Spec.Template.Spec.NodeSelector[core.TPUTopologyAnnotation]; !ok {
		sts.Spec.Template.Spec.NodeSelector[core.TPUTopologyAnnotation] = tpuTopology
	}

	return nil
}
