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
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/klog/v2"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/webhook"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"

	"tpu-slice-controller/internal/features"
)

type PodWebhook struct {
	client client.Client
}

func SetupPodWebhookWithManager(mgr ctrl.Manager) error {
	return ctrl.NewWebhookManagedBy(mgr).
		For(&corev1.Pod{}).
		WithDefaulter(&PodWebhook{
			client: mgr.GetClient(),
		}).
		Complete()
}

// +kubebuilder:webhook:path=/mutate--v1-pod,mutating=true,failurePolicy=fail,sideEffects=None,groups="",resources=pods,verbs=create,versions=v1,name=mpod.kb.io,admissionReviewVersions=v1,objectSelector="cloud.google.com/gke-tpu-slice-pod=true"
// +kubebuilder:rbac:groups=batch,resources=jobs,verbs=get;list;watch
// +kubebuilder:rbac:groups=jobset.x-k8s.io,resources=jobsets,verbs=get;list;watch

var _ webhook.CustomDefaulter = &PodWebhook{}

func (r *PodWebhook) Default(ctx context.Context, obj runtime.Object) error {
	if features.Enabled(features.NodesInSlicesAntiAffinity) {
		pod := obj.(*corev1.Pod)
		log := ctrl.LoggerFrom(ctx).WithName("pod-accelerator-gke-webhook")
		log.V(5).Info("Defaulting Pod", "pod", klog.KObj(pod))
		var isKueueManaged bool

		// Check if the Pod is part of a Kueue-managed JobSet
		if jobSetName, ok := pod.Labels[jobset.JobSetNameKey]; ok {
			var js jobset.JobSet
			if err := r.client.Get(ctx, client.ObjectKey{Name: jobSetName, Namespace: pod.Namespace}, &js); err == nil {
				if js.Labels[kueueconstants.QueueLabel] != "" {
					isKueueManaged = true
				}
			}
		}

		// Check if the Pod is owned by a Kueue-managed Job
		if !isKueueManaged {
			owner := metav1.GetControllerOf(pod)
			if owner != nil && owner.Kind == "Job" {
				var job batchv1.Job
				if err := r.client.Get(ctx, client.ObjectKey{Name: owner.Name, Namespace: pod.Namespace}, &job); err == nil {
					if job.Labels[kueueconstants.QueueLabel] != "" {
						isKueueManaged = true
					}
				}
			}
		}

		if isKueueManaged {
			log.V(5).Info("Removing anti-affinity from pod", "pod", klog.KObj(pod))
			removeNodeInSliceAntiAffinity(&pod.Spec)
		}
	}
	return nil
}
