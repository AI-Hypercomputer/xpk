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
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/util/workqueue"
	"k8s.io/klog/v2"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/event"
	"sigs.k8s.io/controller-runtime/pkg/handler"
	"sigs.k8s.io/controller-runtime/pkg/predicate"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueuealpha "sigs.k8s.io/kueue/apis/kueue/v1alpha1"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	"sigs.k8s.io/kueue/pkg/workload"

	"tpu-slice-controller/api/v1alpha1"
	utilpod "tpu-slice-controller/internal/util/pod"
)

const (
	CleanupSliceFinalizerName   = "accelerator.gke.io/slice"
	TPUReservationSubblockLabel = "cloud.google.com/gke-tpu-reservation-subblock"

	tasLabelValue = "true"
)

var (
	updatesBatchPeriod = time.Second
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
// +kubebuilder:rbac:groups=jobset.x-k8s.io,resources=jobsets,verbs=get;list;watch
// +kubebuilder:rbac:groups="",resources=pods,verbs=get;list;watch

func (r *WorkloadReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	wl := &kueue.Workload{}
	err := r.client.Get(ctx, req.NamespacedName, wl)
	if err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	log := ctrl.LoggerFrom(ctx)
	log.V(2).Info("Reconcile Workload")

	if shouldCleanupSlice(wl) {
		// No need to clean up the Slice or finalize the Workload if it’s already finalized.
		if !controllerutil.ContainsFinalizer(wl, CleanupSliceFinalizerName) {
			return ctrl.Result{}, nil
		}

		cleanedUp, err := r.cleanupSlice(ctx, wl)
		if err != nil || !cleanedUp {
			return ctrl.Result{}, err
		}

		return ctrl.Result{}, client.IgnoreNotFound(r.finalizeWorkload(ctx, wl))
	}

	if controllerutil.AddFinalizer(wl, CleanupSliceFinalizerName) {
		if err := r.client.Update(ctx, wl); err != nil {
			if !errors.IsNotFound(err) {
				log.V(5).Info("Added finalizer")
			}
			return ctrl.Result{}, client.IgnoreNotFound(err)
		}
	}

	return ctrl.Result{}, r.createSliceIfNotExist(ctx, wl)
}

func shouldCleanupSlice(wl *kueue.Workload) bool {
	return !wl.DeletionTimestamp.IsZero() ||
		workload.IsFinished(wl) ||
		workload.IsEvicted(wl) ||
		!workload.IsActive(wl) ||
		!hasSupportedOwner(wl)
}

func hasSupportedOwner(wl *kueue.Workload) bool {
	// For now, we only support JobSets.
	return isJobSetOwner(wl)
}

func isJobSetOwner(wl *kueue.Workload) bool {
	if owner := metav1.GetControllerOf(wl); owner != nil {
		return owner.APIVersion == jobset.SchemeGroupVersion.String() && owner.Kind == "JobSet"
	}
	return false
}

func (r *WorkloadReconciler) cleanupSlice(ctx context.Context, wl *kueue.Workload) (bool, error) {
	slice := r.newEmptySlice(wl)
	err := r.client.Get(ctx, client.ObjectKeyFromObject(slice), slice)
	if client.IgnoreNotFound(err) != nil {
		ctrl.LoggerFrom(ctx).Error(err, "Failed to get Slice")
		return false, err
	}

	//nolint:nilerr // That means that the Slice already deleted.
	if err != nil {
		return true, nil
	}

	terminated, err := r.ownerPodsFinished(ctx, wl)
	if err != nil || !terminated {
		return false, err
	}

	if slice.DeletionTimestamp.IsZero() {
		return false, client.IgnoreNotFound(r.client.Delete(ctx, slice))
	}

	return meta.IsStatusConditionTrue(slice.Status.Conditions, string(v1alpha1.Deformed)), nil
}

func (r *WorkloadReconciler) ownerPodsFinished(ctx context.Context, wl *kueue.Workload) (bool, error) {
	// For now, we only support JobSets.
	if isJobSetOwner(wl) {
		return r.jobSetPodsFinished(ctx, wl)
	}
	// Finalize Workloads that have no owner or have unsupported owner types.
	return true, nil
}

func (r *WorkloadReconciler) jobSetPodsFinished(ctx context.Context, wl *kueue.Workload) (bool, error) {
	owner := metav1.GetControllerOf(wl)
	if owner == nil {
		return true, nil
	}

	log := ctrl.LoggerFrom(ctx).WithValues("jobSet", klog.KRef(wl.Namespace, owner.Name))

	jobSet := &jobset.JobSet{}
	jobSetKey := types.NamespacedName{Name: owner.Name, Namespace: wl.Namespace}
	err := r.client.Get(ctx, jobSetKey, jobSet)
	if err != nil {
		if errors.IsNotFound(err) {
			log.V(5).Info("JobSet not found")
			// That means the JobSet has already been deleted, along with all associated Jobs and Pods
			// we should delete Slice and cleanup Workload.
			return true, nil
		} else {
			log.Error(err, "Failed to get JobSet")
			return false, err
		}
	}

	pods := &corev1.PodList{}
	opts := []client.ListOption{
		client.InNamespace(wl.Namespace),
		client.MatchingLabels{jobset.JobSetNameKey: owner.Name},
	}
	err = r.client.List(ctx, pods, opts...)
	if err != nil {
		return false, err
	}

	for _, pod := range pods.Items {
		if !utilpod.IsTerminated(&pod) {
			log.V(5).Info("Pods are still running – skipping finalization for now")
			return false, nil
		}
	}

	return true, nil
}

func (r *WorkloadReconciler) finalizeWorkload(ctx context.Context, wl *kueue.Workload) error {
	log := ctrl.LoggerFrom(ctx)

	controllerutil.RemoveFinalizer(wl, CleanupSliceFinalizerName)
	if err := r.client.Update(ctx, wl); err != nil {
		if !errors.IsNotFound(err) {
			log.Error(err, "Removing finalizer")
		}
		return err
	}

	log.V(5).Info("Removed finalizer")

	return nil
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

	return r.client.Create(ctx, slice)
}

// SetupWithManager sets up the controller with the Manager.
func (r *WorkloadReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&kueue.Workload{}).
		Named("workload_controller").
		WithEventFilter(r).
		Watches(&v1alpha1.Slice{}, &sliceHandler{client: r.client}).
		Watches(&jobset.JobSet{}, &jobSetHandler{client: r.client}).
		Watches(&corev1.Pod{}, &podHandler{client: r.client}).
		Complete(r)
}

var _ predicate.Predicate = (*WorkloadReconciler)(nil)

func (r *WorkloadReconciler) Create(e event.CreateEvent) bool {
	return r.handleEvent(e.Object)
}

func (r *WorkloadReconciler) Delete(e event.DeleteEvent) bool {
	return r.handleEvent(e.Object)
}

func (r *WorkloadReconciler) Update(e event.UpdateEvent) bool {
	return r.handleEvent(e.ObjectNew)
}

func (r *WorkloadReconciler) Generic(event.GenericEvent) bool {
	// Nothing handle for Generic event.
	return false
}

func shouldHandleWorkload(wl *kueue.Workload) bool {
	// We should handle all Workloads that have the cleanup slice finalizer.
	return controllerutil.ContainsFinalizer(wl, CleanupSliceFinalizerName) || !shouldCleanupSlice(wl)
}

func (r *WorkloadReconciler) handleEvent(obj client.Object) bool {
	wl, isWorkload := obj.(*kueue.Workload)
	if !isWorkload {
		return true
	}
	return shouldHandleWorkload(wl)
}

var _ handler.EventHandler = (*sliceHandler)(nil)

type sliceHandler struct {
	client client.Client
}

func (h *sliceHandler) Generic(context.Context, event.GenericEvent, workqueue.TypedRateLimitingInterface[reconcile.Request]) {
}

func (h *sliceHandler) Create(context.Context, event.CreateEvent, workqueue.TypedRateLimitingInterface[reconcile.Request]) {
}

func (h *sliceHandler) Delete(ctx context.Context, e event.DeleteEvent, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	h.handleEvent(ctx, e.Object, q)
}

func (h *sliceHandler) Update(ctx context.Context, e event.UpdateEvent, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	h.handleEvent(ctx, e.ObjectNew, q)
}

func (h *sliceHandler) handleEvent(ctx context.Context, obj client.Object, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	slice, isSlice := obj.(*v1alpha1.Slice)
	// Only JobSet should be handled.
	if !isSlice {
		return
	}

	log := ctrl.LoggerFrom(ctx)

	owner := metav1.GetControllerOf(slice)
	if owner == nil {
		log.V(5).Info("Owner not found")
		return
	}

	log.V(5).Info("Handle Slice event", "workload", klog.KRef(slice.Namespace, slice.Name))

	req := reconcile.Request{
		NamespacedName: types.NamespacedName{
			Name:      owner.Name,
			Namespace: slice.Namespace,
		},
	}

	q.AddAfter(req, updatesBatchPeriod)
}

var _ handler.EventHandler = (*jobSetHandler)(nil)

type jobSetHandler struct {
	client client.Client
}

func (h *jobSetHandler) Generic(context.Context, event.GenericEvent, workqueue.TypedRateLimitingInterface[reconcile.Request]) {
}

func (h *jobSetHandler) Create(context.Context, event.CreateEvent, workqueue.TypedRateLimitingInterface[reconcile.Request]) {
}

func (h *jobSetHandler) Delete(ctx context.Context, e event.DeleteEvent, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	h.handleEvent(ctx, e.Object, q)
}

func (h *jobSetHandler) Update(context.Context, event.UpdateEvent, workqueue.TypedRateLimitingInterface[reconcile.Request]) {
}

func (h *jobSetHandler) handleEvent(ctx context.Context, obj client.Object, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	jobSet, isJobSet := obj.(*jobset.JobSet)
	// Only JobSet should be handled.
	if !isJobSet {
		return
	}

	log := ctrl.LoggerFrom(ctx).WithValues("jobSet", klog.KRef(jobSet.Namespace, jobSet.Name))
	ctrl.LoggerInto(ctx, log)

	log.V(5).Info("Handle JobSet event")

	handleEventForJobSet(ctx, h.client, jobSet, q)
}

func handleEventForJobSet(ctx context.Context, c client.Client, jobSet *jobset.JobSet, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	log := ctrl.LoggerFrom(ctx)

	workloads := &kueue.WorkloadList{}
	opts := []client.ListOption{
		client.InNamespace(jobSet.Namespace),
		client.MatchingFields{OwnerReferenceUID: string(jobSet.UID)},
	}
	err := c.List(ctx, workloads, opts...)
	if err != nil {
		log.Error(err, "Failed to list workloads")
		return
	}

	if len(workloads.Items) == 0 {
		log.V(5).Info("No Workloads found for the JobSet – skipping handling")
		return
	}

	for _, wl := range workloads.Items {
		if shouldHandleWorkload(&wl) {
			req := reconcile.Request{
				NamespacedName: types.NamespacedName{
					Name:      wl.Name,
					Namespace: wl.Namespace,
				},
			}
			q.AddAfter(req, updatesBatchPeriod)
		}
	}
}

var _ handler.EventHandler = (*podHandler)(nil)

type podHandler struct {
	client client.Client
}

func (h *podHandler) Generic(context.Context, event.GenericEvent, workqueue.TypedRateLimitingInterface[reconcile.Request]) {
}

func (h *podHandler) Create(context.Context, event.CreateEvent, workqueue.TypedRateLimitingInterface[reconcile.Request]) {
}

func (h *podHandler) Delete(ctx context.Context, e event.DeleteEvent, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	h.handleEvent(ctx, e.Object, q)
}

func (h *podHandler) Update(context.Context, event.UpdateEvent, workqueue.TypedRateLimitingInterface[reconcile.Request]) {
}

func (h *podHandler) handleEvent(ctx context.Context, obj client.Object, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	pod, isPod := obj.(*corev1.Pod)
	// Only Pods and Pods with the TAS label should be handled.
	if !isPod || pod.Labels[kueuealpha.TASLabel] != tasLabelValue {
		return
	}

	jobSetName := pod.Labels[jobset.JobSetNameKey]
	// Only pods owned by a JobSet should be handled.
	if jobSetName == "" {
		return
	}

	log := ctrl.LoggerFrom(ctx).WithValues(
		"pod", klog.KObj(pod),
		"jobSet", klog.KRef(pod.Namespace, jobSetName),
	)
	ctrl.LoggerInto(ctx, log)

	log.V(5).Info("Handle Pod event")

	jobSet := &jobset.JobSet{}
	jobSetKey := types.NamespacedName{Name: jobSetName, Namespace: pod.Namespace}
	err := h.client.Get(ctx, jobSetKey, jobSet)
	if err != nil {
		if errors.IsNotFound(err) {
			log.V(5).Info("JobSet not found")
		} else {
			log.Error(err, "Failed to get JobSet")
		}
		return
	}

	handleEventForJobSet(ctx, h.client, jobSet, q)
}
