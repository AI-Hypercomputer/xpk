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
	"slices"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	"sigs.k8s.io/kueue/pkg/workload"

	"tpu-slice-controller/api/v1alpha1"
)

const (
	CleanupSliceFinalizerName   = "accelerator.gke.io/slice"
	TPUReservationSubblockLabel = "cloud.google.com/gke-tpu-reservation-subblock"
)

// WorkloadReconciler reconciles a Workload object
type WorkloadReconciler struct {
	client client.Client
}

var _ reconcile.Reconciler = (*WorkloadReconciler)(nil)

func NewWorkloadReconciler(cl client.Client) *WorkloadReconciler {
	return &WorkloadReconciler{
		client: cl,
	}
}

// +kubebuilder:rbac:groups=kueue.x-k8s.io,resources=workloads,verbs=get;list;watch;create;update;patch
// +kubebuilder:rbac:groups=slice.accelerator.gke.io,resources=slices,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=slice.accelerator.gke.io,resources=slices/finalizers,verbs=update

func (r *WorkloadReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	wl := &kueue.Workload{}
	err := r.client.Get(ctx, req.NamespacedName, wl)
	if err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	log := ctrl.LoggerFrom(ctx)
	log.V(2).Info("Reconcile Workload")

	if r.shouldFinalize(wl) {
		if controllerutil.ContainsFinalizer(wl, CleanupSliceFinalizerName) {
			err = r.client.Delete(ctx, r.newEmptySlice(wl))
			if client.IgnoreNotFound(err) != nil {
				return ctrl.Result{}, err
			}
			controllerutil.RemoveFinalizer(wl, CleanupSliceFinalizerName)
			if err := r.client.Update(ctx, wl); err != nil {
				return ctrl.Result{}, err
			}
			log.V(5).Info("Removed finalizer")
		}
		return ctrl.Result{}, nil
	}

	if controllerutil.AddFinalizer(wl, CleanupSliceFinalizerName) {
		if err := r.client.Update(ctx, wl); err != nil {
			log.V(5).Info("Added finalizer")
			return ctrl.Result{}, err
		}
	}

	return ctrl.Result{}, r.createSliceIfNotExist(ctx, wl)
}

func (r *WorkloadReconciler) shouldFinalize(wl *kueue.Workload) bool {
	return !wl.DeletionTimestamp.IsZero() || workload.IsFinished(wl) || workload.IsEvicted(wl) || !workload.IsActive(wl)
}

func (r *WorkloadReconciler) newEmptySlice(wl *kueue.Workload) *v1alpha1.Slice {
	return &v1alpha1.Slice{
		ObjectMeta: metav1.ObjectMeta{
			Name:      wl.Name,
			Namespace: wl.Namespace,
		},
	}
}

func (r *WorkloadReconciler) newSlice(wl *kueue.Workload) (*v1alpha1.Slice, error) {
	slice := r.newEmptySlice(wl)

	if err := controllerutil.SetControllerReference(wl, slice, r.client.Scheme()); err != nil {
		return nil, err
	}

	if wl.Status.Admission != nil && wl.Status.Admission.PodSetAssignments != nil {
		for _, psa := range wl.Status.Admission.PodSetAssignments {
			if psa.TopologyAssignment != nil {
				for _, domain := range psa.TopologyAssignment.Domains {
					if slice.Spec.NodeSelector == nil {
						slice.Spec.NodeSelector = make(map[string][]string)
					}
					if slice.Spec.NodeSelector[TPUReservationSubblockLabel] == nil {
						slice.Spec.NodeSelector[TPUReservationSubblockLabel] = []string{}
					}
					// make sure there are no duplicates in the nodeSelector
					for _, v := range domain.Values {
						exists := slices.Contains(slice.Spec.NodeSelector[TPUReservationSubblockLabel], v)
						if !exists {
							slice.Spec.NodeSelector[TPUReservationSubblockLabel] = append(slice.Spec.NodeSelector[TPUReservationSubblockLabel], v)
						}
					}
				}
			}
		}
	}

	return slice, nil
}

func (r *WorkloadReconciler) createSliceIfNotExist(ctx context.Context, wl *kueue.Workload) error {
	slice := r.newEmptySlice(wl)

	err := r.client.Get(ctx, client.ObjectKeyFromObject(slice), slice)
	if client.IgnoreNotFound(err) != nil {
		return err
	}
	if err == nil {
		return nil
	}

	slice, err = r.newSlice(wl)
	if err != nil {
		return err
	}

	// We should wait for TopologyAssignments.
	if len(slice.Spec.NodeSelector) == 0 {
		log := ctrl.LoggerFrom(ctx)
		log.V(2).Info("Workload does not have TopologyAssignments. Skipping Slice creation for now.")
		return nil
	}

	return r.client.Create(ctx, slice)
}

// SetupWithManager sets up the controller with the Manager.
func (r *WorkloadReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&kueue.Workload{}).
		Named("workload").
		Complete(r)
}
