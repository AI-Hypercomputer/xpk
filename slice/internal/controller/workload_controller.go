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
	"errors"
	"fmt"
	"maps"
	"slices"

	"golang.org/x/sync/errgroup"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/sets"
	"k8s.io/klog/v2"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	"sigs.k8s.io/kueue/pkg/workload"

	"tpu-slice-controller/api/v1alpha1"
	"tpu-slice-controller/internal/util/parallelize"
)

const (
	CleanupSliceFinalizerName   = "accelerator.gke.io/slice"
	TPUReservationSubBlockLabel = "cloud.google.com/gke-tpu-reservation-subblock"
	NodePoolLabel               = "cloud.google.com/gke-nodepool"
	TPUTopologyLabel            = "cloud.google.com/gke-tpu-topology"
	TPUAcceleratorLabel         = "cloud.google.com/gke-tpu-accelerator"
)

var (
	errPodSetNotFound              = errors.New("PodSet not found")
	errPodSetAssignmentNotFound    = errors.New("PodSetAssignment not found")
	errTPUTopologyLabelNotFound    = fmt.Errorf("%s label not found", TPUTopologyLabel)
	errTPUAcceleratorLabelNotFound = fmt.Errorf("%s label not found", TPUAcceleratorLabel)
	errTopologyAssignmentNotFound  = errors.New("TopologyAssignment not found")
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
		return ctrl.Result{}, client.IgnoreNotFound(r.finalize(ctx, wl))
	}

	if controllerutil.AddFinalizer(wl, CleanupSliceFinalizerName) {
		if err := r.client.Update(ctx, wl); err != nil {
			log.V(5).Info("Added finalizer")
			return ctrl.Result{}, err
		}
	}

	return ctrl.Result{}, r.createSlicesIfNotExist(ctx, wl)
}

func (r *WorkloadReconciler) shouldFinalize(wl *kueue.Workload) bool {
	return !wl.DeletionTimestamp.IsZero() || workload.IsFinished(wl) || workload.IsEvicted(wl) || !workload.IsActive(wl)
}

func (r *WorkloadReconciler) finalize(ctx context.Context, wl *kueue.Workload) error {
	if !controllerutil.ContainsFinalizer(wl, CleanupSliceFinalizerName) {
		return nil
	}

	log := ctrl.LoggerFrom(ctx)

	slices, err := r.findWorkloadSlices(ctx, wl)
	if err != nil {
		log.Error(err, "Failed to find Slices")
		return err
	}

	err = parallelize.Until(ctx, len(slices), func(i int) error {
		slice := &slices[i]
		err = r.client.Delete(ctx, slice)
		if client.IgnoreNotFound(err) != nil {
			log.Error(err, "Failed to delete the Slice", "slice", klog.KObj(slice))
			return err
		}
		return nil
	})
	if err != nil {
		return err
	}

	controllerutil.RemoveFinalizer(wl, CleanupSliceFinalizerName)
	if err := r.client.Update(ctx, wl); err != nil {
		if !apierrors.IsNotFound(err) {
			log.Error(err, "Failed to remove finalizer")
		}
		return err
	}

	log.V(5).Info("Removed finalizer")

	return nil
}

func (r *WorkloadReconciler) findWorkloadSlices(ctx context.Context, wl *kueue.Workload) ([]v1alpha1.Slice, error) {
	slices := &v1alpha1.SliceList{}
	opts := []client.ListOption{
		client.InNamespace(wl.Namespace),
		client.MatchingFields{OwnerReferenceUID: string(wl.UID)},
	}
	if err := r.client.List(ctx, slices, opts...); err != nil {
		return nil, err
	}
	return slices.Items, nil
}

func (r *WorkloadReconciler) createSlicesIfNotExist(ctx context.Context, wl *kueue.Workload) error {
	log := ctrl.LoggerFrom(ctx)

	createdSlices, err := r.findWorkloadSlices(ctx, wl)
	if err != nil {
		log.Error(err, "Failed to find Slices")
		return err
	}

	createdSlicesByName := make(map[string]*v1alpha1.Slice, len(createdSlices))
	for _, slice := range createdSlices {
		createdSlicesByName[slice.Name] = &slice
	}

	var toCreate []*v1alpha1.Slice

	if wl.Status.Admission != nil {
		for _, psa := range wl.Status.Admission.PodSetAssignments {
			sliceName := GetSliceName(wl.Name, psa.Name)

			if _, ok := createdSlicesByName[sliceName]; ok {
				delete(createdSlicesByName, sliceName)
				continue
			}

			slice, err := newSlice(wl, psa.Name)
			if err != nil {
				if !isUnsupportedPodSetError(err) {
					log.Error(err, "Failed to create a Slice")
					return err
				}
				log.V(8).Info("Failed to create Slice", "error", err)
				continue
			}

			if err := controllerutil.SetControllerReference(wl, slice, r.client.Scheme()); err != nil {
				return err
			}

			toCreate = append(toCreate, slice)
		}
	}

	eg, ctx := errgroup.WithContext(ctx)

	eg.Go(func() error {
		return parallelize.Until(ctx, len(toCreate), func(i int) error {
			slice := toCreate[i]
			err = r.client.Create(ctx, slice)
			if err != nil {
				log.Error(err, "Failed to create a Slice", "slice", klog.KObj(slice))
				return err
			}
			return nil
		})
	})

	toDelete := slices.Collect(maps.Values(createdSlicesByName))
	eg.Go(func() error {
		return parallelize.Until(ctx, len(toDelete), func(i int) error {
			slice := toDelete[i]
			err = r.client.Delete(ctx, slice)
			if client.IgnoreNotFound(err) != nil {
				log.Error(err, "Failed to delete the redundant Slice", "slice", klog.KObj(slice))
				return err
			}
			return nil
		})
	})

	return eg.Wait()
}

func GetSliceName(workloadName string, podSetName kueue.PodSetReference) string {
	return fmt.Sprintf("%s-%s", workloadName, podSetName)
}

func newSlice(wl *kueue.Workload, podSetName kueue.PodSetReference) (*v1alpha1.Slice, error) {
	ps := findPodSet(wl, podSetName)
	if findPodSet(wl, podSetName) == nil {
		return nil, errPodSetNotFound
	}

	if ps.Template.Spec.NodeSelector[TPUTopologyLabel] == "" {
		return nil, errTPUTopologyLabelNotFound
	}

	if ps.Template.Spec.NodeSelector[TPUAcceleratorLabel] == "" {
		return nil, errTPUAcceleratorLabelNotFound
	}

	psa := findPodSetAssignment(wl, podSetName)
	if psa == nil {
		return nil, errPodSetAssignmentNotFound
	}

	if psa.TopologyAssignment == nil {
		return nil, errTopologyAssignmentNotFound
	}

	slice := &v1alpha1.Slice{
		ObjectMeta: metav1.ObjectMeta{
			Name:      GetSliceName(wl.Name, podSetName),
			Namespace: wl.Namespace,
		},
		Spec: v1alpha1.SliceSpec{
			AcceleratorTopology: ps.Template.Spec.NodeSelector[TPUTopologyLabel],
			AcceleratorType:     ps.Template.Spec.NodeSelector[TPUAcceleratorLabel],
			NodeSelector:        make(map[string][]string),
		},
	}

	for _, domain := range psa.TopologyAssignment.Domains {
		if ps.Template.Spec.NodeSelector[TPUReservationSubBlockLabel] != "" {
			subBlockDomains := sets.New[string](domain.Values...)
			if subBlockDomains.Len() > 0 {
				slice.Spec.NodeSelector[TPUReservationSubBlockLabel] = sets.List(subBlockDomains)
			}
		}
		if ps.Template.Spec.NodeSelector[NodePoolLabel] != "" {
			nodePoolDomains := sets.New[string](domain.Values...)
			if nodePoolDomains.Len() > 0 {
				slice.Spec.NodeSelector[NodePoolLabel] = sets.List(nodePoolDomains)
			}
		}
	}

	return slice, nil
}

func findPodSet(wl *kueue.Workload, podSetName kueue.PodSetReference) *kueue.PodSet {
	for _, ps := range wl.Spec.PodSets {
		if ps.Name == podSetName {
			return &ps
		}
	}
	return nil
}

func findPodSetAssignment(wl *kueue.Workload, podSetName kueue.PodSetReference) *kueue.PodSetAssignment {
	for _, psa := range wl.Status.Admission.PodSetAssignments {
		if psa.Name == podSetName {
			return &psa
		}
	}
	return nil
}

func isUnsupportedPodSetError(err error) bool {
	return errors.Is(err, errTPUTopologyLabelNotFound) ||
		errors.Is(err, errTPUAcceleratorLabelNotFound) ||
		errors.Is(err, errTopologyAssignmentNotFound)
}

// SetupWithManager sets up the controller with the Manager.
func (r *WorkloadReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&kueue.Workload{}).
		Named("workload_controller").
		Complete(r)
}
