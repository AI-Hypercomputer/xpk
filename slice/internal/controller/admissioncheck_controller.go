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

package controller

import (
	"context"

	apimeta "k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/utils/ptr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
)

type AdmissionCheckReconciler struct {
	client client.Client
}

var _ reconcile.Reconciler = (*AdmissionCheckReconciler)(nil)

func NewAdmissionCheckReconciler(cl client.Client) *AdmissionCheckReconciler {
	return &AdmissionCheckReconciler{
		client: cl,
	}
}

// +kubebuilder:rbac:groups=kueue.x-k8s.io,resources=admissionchecks,verbs=get;list;watch
// +kubebuilder:rbac:groups=kueue.x-k8s.io,resources=admissionchecks/status,verbs=get;update;patch

func (r *AdmissionCheckReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	ac := &kueue.AdmissionCheck{}
	if err := r.client.Get(ctx, req.NamespacedName, ac); err != nil || ac.Spec.ControllerName != SliceControllerName {
		return reconcile.Result{}, client.IgnoreNotFound(err)
	}

	log := ctrl.LoggerFrom(ctx)
	log.V(2).Info("Reconcile AdmissionCheck")

	currentCondition := ptr.Deref(apimeta.FindStatusCondition(ac.Status.Conditions, kueue.AdmissionCheckActive), metav1.Condition{})
	newCondition := metav1.Condition{
		Type:               kueue.AdmissionCheckActive,
		Status:             metav1.ConditionTrue,
		Reason:             "Active",
		Message:            "The admission check is active",
		ObservedGeneration: ac.Generation,
	}

	if currentCondition.Status != newCondition.Status {
		apimeta.SetStatusCondition(&ac.Status.Conditions, newCondition)
		return reconcile.Result{}, client.IgnoreNotFound(r.client.Status().Update(ctx, ac))
	}

	return reconcile.Result{}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *AdmissionCheckReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&kueue.AdmissionCheck{}).
		Named("admissioncheck_controller").
		Complete(r)
}
