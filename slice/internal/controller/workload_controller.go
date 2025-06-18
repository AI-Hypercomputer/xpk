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

package controller

import (
	"context"
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	"tpu-slice-controller/api/v1alpha1"
)

// WorkloadReconciler reconciles a Workload object
type WorkloadReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

func (r *WorkloadReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	var wl kueue.Workload
	if err := r.Get(ctx, req.NamespacedName, &wl); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	log := ctrl.LoggerFrom(ctx)
	log.V(2).Info("Reconcile Workload")

	sliceName := fmt.Sprintf("%s-slice", wl.Name)
	if !wl.DeletionTimestamp.IsZero() {
		if controllerutil.ContainsFinalizer(&wl, v1alpha1.CleanupSliceFinalizerName) {
			if err := r.deleteSlice(ctx, sliceName, wl.Namespace); err != nil {
				return ctrl.Result{}, err
			}

			controllerutil.RemoveFinalizer(&wl, v1alpha1.CleanupSliceFinalizerName)
			if err := r.Update(ctx, &wl); err != nil {
				return ctrl.Result{}, err
			}
			log.V(5).Info("Removed finalizer")
		}
		return ctrl.Result{}, nil
	}

	if controllerutil.AddFinalizer(&wl, v1alpha1.CleanupSliceFinalizerName) {
		if err := r.Update(ctx, &wl); err != nil {
			log.V(5).Info("Added finalizer")
			return ctrl.Result{}, err
		}

		return ctrl.Result{}, nil
	}

	return ctrl.Result{}, nil
}

func (r *WorkloadReconciler) deleteSlice(ctx context.Context, name, ns string) error {
	slice := &v1alpha1.Slice{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: ns,
		},
	}
	err := r.Delete(ctx, slice)

	return client.IgnoreNotFound(err)
}

// SetupWithManager sets up the controller with the Manager.
func (r *WorkloadReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&kueue.Workload{}).
		Named("workload").
		Complete(r)
}
