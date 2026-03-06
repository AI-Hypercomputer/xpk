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

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/klog/v2"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/webhook"

	"tpu-slice-controller/internal/features"
)

type PodWebhook struct {
}

func SetupPodWebhookWithManager(mgr ctrl.Manager) error {
	return ctrl.NewWebhookManagedBy(mgr).
		For(&corev1.Pod{}).
		WithDefaulter(&PodWebhook{}).
		Complete()
}

// +kubebuilder:webhook:path=/mutate--v1-pod,mutating=true,failurePolicy=fail,sideEffects=None,groups="",resources=pods,verbs=create,versions=v1,name=mpod.accelerator.gke.io,admissionReviewVersions=v1

var _ webhook.CustomDefaulter = &PodWebhook{}

func (r *PodWebhook) Default(ctx context.Context, obj runtime.Object) error {
	if features.Enabled(features.NodesInSlicesAntiAffinity) {
		pod := obj.(*corev1.Pod)
		log := ctrl.LoggerFrom(ctx).WithName("pod-accelerator-gke-webhook")
		log.V(5).Info("Defaulting pod by removing anti-affinity", "pod", klog.KObj(pod))
		removeNodeInSliceAntiAffinity(&pod.Spec)
	}
	return nil
}
