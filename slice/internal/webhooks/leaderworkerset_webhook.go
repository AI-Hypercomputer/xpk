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

	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/webhook"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"
	leaderworkersetv1 "sigs.k8s.io/lws/api/leaderworkerset/v1"

	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/topology"
)

const (
	podsetGroupName  = "kueue.x-k8s.io/podset-group-name"
	podsetGroupValue = "lws-super-slice-group"
)

type LeaderWorkerSetWebhook struct {
	DefaultSliceHealthValues []string
}

func SetupLeaderWorkerSetWebhookWithManager(mgr ctrl.Manager, defaultSliceHealthValues []string) error {
	return ctrl.NewWebhookManagedBy(mgr).
		For(&leaderworkersetv1.LeaderWorkerSet{}).
		WithDefaulter(&LeaderWorkerSetWebhook{
			DefaultSliceHealthValues: defaultSliceHealthValues,
		}).
		Complete()
}

// +kubebuilder:webhook:path=/mutate-leaderworkerset-x-k8s-io-v1-leaderworkerset,mutating=true,failurePolicy=fail,sideEffects=None,groups=leaderworkerset.x-k8s.io,resources=leaderworkersets,verbs=create,versions=v1,name=mleaderworkerset.kb.io,admissionReviewVersions=v1

var _ webhook.CustomDefaulter = &LeaderWorkerSetWebhook{}

func (r *LeaderWorkerSetWebhook) Default(ctx context.Context, obj runtime.Object) error {
	lws := obj.(*leaderworkersetv1.LeaderWorkerSet)
	log := ctrl.LoggerFrom(ctx).WithName("leaderworkerset-accelerator-gke-webhook")
	log.V(5).Info("Defaulting LeaderWorkerSet")

	if lws.Labels[kueueconstants.QueueLabel] == "" {
		log.V(5).Info("Skipping due to missing Kueue Label")
		return nil
	}

	if !core.IsRelevantPodTemplateSpec(lws.Spec.LeaderWorkerTemplate.WorkerTemplate) {
		log.V(5).Info("Skipping annotating LeaderWorkerTemplate due to TPU Annotation or Node Selector misconfigured at worker template")
		return nil
	}
	if lws.Spec.LeaderWorkerTemplate.LeaderTemplate != nil && !core.IsRelevantPodTemplateSpec(*lws.Spec.LeaderWorkerTemplate.LeaderTemplate) {
		log.V(5).Info("Skipping annotating LeaderWorkerTemplate due to TPU Annotation or Node Selector misconfigured at leader template")
		return nil
	}

	log.V(5).Info("Annotating WorkerTemplate")
	tpuTopology := lws.Spec.LeaderWorkerTemplate.WorkerTemplate.Annotations[core.TPUSliceTopologyAnnotation]
	parsed, err := topology.ParseTopologyV7(tpuTopology)
	if err != nil {
		return err
	}
	annotatePodTemplateSpecWithSliceHealth(&lws.Spec.LeaderWorkerTemplate.WorkerTemplate, parsed, r.DefaultSliceHealthValues)
	if lws.Spec.LeaderWorkerTemplate.WorkerTemplate.Annotations == nil {
		lws.Spec.LeaderWorkerTemplate.WorkerTemplate.Annotations = make(map[string]string)
	}
	if lws.Spec.LeaderWorkerTemplate.LeaderTemplate != nil {
		// if the leader is defined, annotate both templates with the same group name
		lws.Spec.LeaderWorkerTemplate.WorkerTemplate.Annotations[podsetGroupName] = podsetGroupValue
		lws.Spec.LeaderWorkerTemplate.LeaderTemplate.Annotations[podsetGroupName] = podsetGroupValue

		annotatePodTemplateSpecWithSliceHealth(lws.Spec.LeaderWorkerTemplate.LeaderTemplate, parsed, r.DefaultSliceHealthValues)
		if lws.Spec.LeaderWorkerTemplate.LeaderTemplate.Annotations == nil {
			lws.Spec.LeaderWorkerTemplate.LeaderTemplate.Annotations = make(map[string]string)
		}
		lws.Spec.LeaderWorkerTemplate.LeaderTemplate.Annotations[kueue.PodSetRequiredTopologyAnnotation] = parsed.RequiredSliceLevel()
	}

	lws.Spec.LeaderWorkerTemplate.WorkerTemplate.Annotations[kueue.PodSetRequiredTopologyAnnotation] = parsed.RequiredSliceLevel()
	return nil
}
