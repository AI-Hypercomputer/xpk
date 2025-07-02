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
	"time"

	"github.com/go-logr/logr"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/sets"
	"k8s.io/client-go/tools/record"
	"k8s.io/client-go/util/workqueue"
	"k8s.io/klog/v2"
	"k8s.io/utils/clock"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/event"
	"sigs.k8s.io/controller-runtime/pkg/handler"
	"sigs.k8s.io/controller-runtime/pkg/predicate"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	"sigs.k8s.io/kueue/pkg/util/admissioncheck"
	"sigs.k8s.io/kueue/pkg/workload"

	"tpu-slice-controller/api/v1alpha1"
	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/topology"
	"tpu-slice-controller/internal/util/api"
	utilpod "tpu-slice-controller/internal/util/pod"
)

const (
	SliceControllerName         = "accelerator.gke.io/slice"
	TPUReservationSubblockLabel = "cloud.google.com/gke-tpu-reservation-subblock"

	SliceCreatedEventType          = "SliceCreated"
	FailedCreateSliceEventType     = "FailedCreateSlice"
	AdmissionCheckUpdatedEventType = "AdmissionCheckUpdated"
)

const (
	updatesBatchPeriod = time.Second
	cleanupRetryAfter  = 5 * time.Second
)

var (
	realClock = clock.RealClock{}
)

// WorkloadReconciler reconciles a Workload object
type WorkloadReconciler struct {
	client client.Client
	record record.EventRecorder
	clock  clock.Clock
}

var _ reconcile.Reconciler = (*WorkloadReconciler)(nil)

func NewWorkloadReconciler(cl client.Client, record record.EventRecorder) *WorkloadReconciler {
	return &WorkloadReconciler{
		client: cl,
		record: record,
		clock:  realClock,
	}
}

// +kubebuilder:rbac:groups=kueue.x-k8s.io,resources=workloads,verbs=get;list;watch;create;update;patch
// +kubebuilder:rbac:groups=kueue.x-k8s.io,resources=workloads/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=slice.accelerator.gke.io,resources=slices,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=slice.accelerator.gke.io,resources=slices/finalizers,verbs=update
// +kubebuilder:rbac:groups="",resources=events,verbs=create;watch;update;patch
// +kubebuilder:rbac:groups=jobset.x-k8s.io,resources=jobsets,verbs=get;list;watch
// +kubebuilder:rbac:groups="",resources=pods,verbs=get;list;watch

func (r *WorkloadReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	wl := &kueue.Workload{}
	err := r.client.Get(ctx, req.NamespacedName, wl)
	if err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	log := ctrl.LoggerFrom(ctx)
	log.V(3).Info("Reconcile Workload")

	if finalize, reason := shouldFinalize(wl); finalize {
		log.V(3).Info(fmt.Sprintf("Cleaning up the Slice and finalize the Workload because %s", reason))
		cleanedUp, err := r.cleanupSlice(ctx, wl)
		if err != nil {
			return ctrl.Result{}, err
		}
		if !cleanedUp {
			return ctrl.Result{RequeueAfter: cleanupRetryAfter}, err
		}
		err = r.finalizeWorkload(ctx, wl)
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	if err = validateRelevantWorkload(wl); err != nil {
		log.V(3).Info(fmt.Sprintf("Skipping workload as it %s", err.Error()))
		return ctrl.Result{}, nil
	}

	ac, err := r.sliceAC(ctx, wl)
	if err != nil {
		return reconcile.Result{}, err
	}
	if ac == nil {
		log.V(3).Info("Admission check not found - skipping reconciliation")
		return reconcile.Result{}, nil
	}

	log = log.WithValues("admissionCheck", ac.Name)
	ctrl.LoggerInto(ctx, log)

	if controllerutil.AddFinalizer(wl, SliceControllerName) {
		if err = r.client.Update(ctx, wl); err != nil {
			if !apierrors.IsNotFound(err) {
				log.Error(err, "Failed to add finalizer")
			}
			return ctrl.Result{}, client.IgnoreNotFound(err)
		}
		log.V(3).Info("Added finalizer")
		return ctrl.Result{}, nil
	}

	slice := v1alpha1.Slice{}
	err = r.client.Get(ctx, core.SliceKeyFromWorkload(wl), &slice)
	if apierrors.IsNotFound(err) {
		// slice not found, create it and exit.
		err = r.createSlice(ctx, log, wl, ac)
		return ctrl.Result{}, err
	} else if err != nil {
		// error fetching slice
		log.Error(err, "Failed to fetch the Slice")
		return ctrl.Result{}, err
	}

	err = r.syncAdmissionCheckStatus(ctx, wl, ac, &slice)
	return ctrl.Result{}, client.IgnoreNotFound(err)
}

func shouldFinalize(wl *kueue.Workload) (bool, string) {
	if !wl.DeletionTimestamp.IsZero() {
		return true, "it has been deleted"
	}

	if workload.IsFinished(wl) {
		return true, "it has finished"
	}

	if workload.IsEvicted(wl) {
		return true, "it was evicted"
	}

	if !workload.IsActive(wl) {
		return true, "it is no longer active"
	}

	if !controllerutil.HasControllerReference(wl) {
		return true, "it doesn't have owner"
	}

	if !hasSupportedOwner(wl) {
		return true, "it has an unsupported owner"
	}

	return false, ""
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
	slice := v1alpha1.Slice{}
	sliceKey := core.SliceKeyFromWorkload(wl)

	log := ctrl.LoggerFrom(ctx).WithValues("slice", klog.KRef(sliceKey.Namespace, sliceKey.Name))
	ctrl.LoggerInto(ctx, log)

	err := r.client.Get(ctx, sliceKey, &slice)
	if apierrors.IsNotFound(err) {
		// slice not found
		return true, nil
	} else if err != nil {
		// error fetching slice
		log.Error(err, "Failed to fetch the Slice")
		return false, err
	}

	if !slice.DeletionTimestamp.IsZero() {
		log.V(3).Info("Slice already deleted, finishing cleanup")
		return true, nil
	}

	if !core.Deformed(&slice) {
		terminated, err := r.ownerPodsFinished(ctx, wl)
		if err != nil || !terminated {
			return false, err
		}
	} else {
		log.V(3).Info("Slice in deformed state")
		// We still need to delete the Slice because requeueing causes a conflict error during Slice creation.
	}

	log.V(3).Info("Deleting the Slice")

	err = r.client.Delete(ctx, &slice)
	if apierrors.IsNotFound(err) {
		return true, nil
	} else if err != nil {
		log.Error(err, "Failed to delete the Slice")
	}

	return true, err
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
	log := ctrl.LoggerFrom(ctx).WithValues("jobSet", klog.KRef(wl.Namespace, owner.Name))
	jobSet := &jobset.JobSet{}
	jobSetKey := types.NamespacedName{Name: owner.Name, Namespace: wl.Namespace}
	if err := r.client.Get(ctx, jobSetKey, jobSet); err != nil {
		if apierrors.IsNotFound(err) {
			log.V(3).Info("JobSet already deleted")
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
	if err := r.client.List(ctx, pods, opts...); err != nil {
		log.Error(err, "Failed to get Pods")
		return false, err
	}

	for _, pod := range pods.Items {
		if !utilpod.IsTerminated(&pod) {
			log.V(3).Info("Pods are still running – skipping finalization for now")
			return false, nil
		}
	}

	log.V(3).Info("All Pods in the JobSet have finished")

	return true, nil
}

func (r *WorkloadReconciler) finalizeWorkload(ctx context.Context, wl *kueue.Workload) error {
	log := ctrl.LoggerFrom(ctx)

	controllerutil.RemoveFinalizer(wl, SliceControllerName)
	if err := r.client.Update(ctx, wl); err != nil {
		if !apierrors.IsNotFound(err) {
			log.Error(err, "Failed to remove the finalizer")
		}
		return err
	}

	log.V(3).Info("Removed finalizer")

	return nil
}

func validateRelevantWorkload(wl *kueue.Workload) error {
	if !hasSupportedOwner(wl) {
		return errors.New("does not have a supported owner")
	}
	if !hasRelevantPodSet(wl.Spec.PodSets) {
		return errors.New("does not have a relevant podset")
	}
	if !workload.HasQuotaReservation(wl) {
		return errors.New("does not have a quota reservation")
	}
	if wl.Status.Admission == nil {
		return errors.New("has no admission")
	}
	if !topology.AnyAssignment(wl.Status.Admission) {
		return errors.New("has no topology assignment")
	}
	if !topology.AllAssignmentsValid(wl.Status.Admission) {
		return errors.New("has invalid topology assignments")
	}
	return nil
}

func hasRelevantPodSet(podSets []kueue.PodSet) bool {
	// At least one PodSet should be relevant.
	for _, ps := range podSets {
		if core.IsRelevantPodTemplateSpec(ps.Template) {
			return true
		}
	}
	return false
}

func (r *WorkloadReconciler) sliceAC(ctx context.Context, wl *kueue.Workload) (*kueue.AdmissionCheckState, error) {
	relevantChecks, err := admissioncheck.FilterForController(ctx, r.client, wl.Status.AdmissionChecks, SliceControllerName)
	if err != nil {
		return nil, err
	}
	if len(relevantChecks) == 0 {
		return nil, nil
	}
	if len(relevantChecks) > 1 {
		ctrl.LoggerFrom(ctx).V(2).Info(
			"WARNING: More than one AdmissionCheck found. Using the first one",
			"selected", relevantChecks[0],
		)
	}
	return workload.FindAdmissionCheck(wl.Status.AdmissionChecks, relevantChecks[0]), nil
}

func parseTopologyAssignmentIntoNodeSelector(slice *v1alpha1.Slice, wl *kueue.Workload) {
	nodeSelectors := sets.New[string]()
	for _, psa := range wl.Status.Admission.PodSetAssignments {
		// we already validated that all assignments have a valid level,
		// in validateRelevantWorkload.
		subblockLevelIndex := topology.SubblockLevelIndex(&psa)
		for _, domain := range psa.TopologyAssignment.Domains {
			nodeSelectors.Insert(domain.Values[subblockLevelIndex])
		}
	}
	slice.Spec.NodeSelector = map[string][]string{
		TPUReservationSubblockLabel: sets.List(nodeSelectors),
	}
}

func (r *WorkloadReconciler) createSlice(ctx context.Context, log logr.Logger, wl *kueue.Workload, ac *kueue.AdmissionCheckState) error {
	slice := core.SliceWithMetadata(wl)
	log = log.WithValues("slice", klog.KObj(slice))
	log.V(3).Info("Creating Slice")

	if err := controllerutil.SetControllerReference(wl, slice, r.client.Scheme()); err != nil {
		return err
	}
	parseTopologyAssignmentIntoNodeSelector(slice, wl)

	if err := r.client.Create(ctx, slice); err != nil {
		msg := fmt.Sprintf("Error creating Slice %q: %v", slice.Name, err)
		log.Error(err, msg)
		r.record.Event(wl, corev1.EventTypeWarning, FailedCreateSliceEventType, api.TruncateEventMessage(msg))
		ac.Message = api.TruncateConditionMessage(msg)
		patchErr := r.updateWorkloadAdmissionCheckStatus(ctx, wl, ac)
		return errors.Join(err, patchErr)
	}

	msg := fmt.Sprintf("The Slice %s has been created", client.ObjectKeyFromObject(slice))
	log.V(3).Info(msg)
	r.record.Event(wl, corev1.EventTypeNormal, SliceCreatedEventType, msg)
	ac.Message = msg

	return r.updateWorkloadAdmissionCheckStatus(ctx, wl, ac)
}

func (r *WorkloadReconciler) updateWorkloadAdmissionCheckStatus(ctx context.Context, wl *kueue.Workload, ac *kueue.AdmissionCheckState) error {
	wlPatch := workload.BaseSSAWorkload(wl)
	workload.SetAdmissionCheckState(&wlPatch.Status.AdmissionChecks, *ac, r.clock)
	err := r.client.Status().Patch(ctx, wlPatch, client.Apply, client.FieldOwner(SliceControllerName), client.ForceOwnership)
	if err != nil && !apierrors.IsNotFound(err) {
		ctrl.LoggerFrom(ctx).Error(err, "Failed to patch the Workload's admission status")
	}
	return err
}

// syncAdmissionCheckStatus syncs the admission check status with the state of the slice.
func (r *WorkloadReconciler) syncAdmissionCheckStatus(ctx context.Context, wl *kueue.Workload, ac *kueue.AdmissionCheckState, slice *v1alpha1.Slice) error {
	originalState := ac.State

	errCond := meta.FindStatusCondition(slice.Status.Conditions, string(v1alpha1.Error))

	switch {
	case core.Forming(slice):
		ac.Message = fmt.Sprintf("The Slice %q is being formed", slice.Name)
	case core.Ready(slice):
		ac.State = kueue.CheckStateReady
		ac.Message = fmt.Sprintf("The Slice %q is fully operational", slice.Name)
	case core.Degraded(slice):
		ac.State = kueue.CheckStateReady
		ac.Message = fmt.Sprintf("The Slice %q is running with reduced capacity or performance", slice.Name)
	case core.Deformed(slice):
		ac.State = kueue.CheckStateRejected
		ac.Message = fmt.Sprintf("The Slice %q is being torn down", slice.Name)
	case errCond != nil && errCond.Status == metav1.ConditionTrue:
		ac.State = kueue.CheckStateRejected
		ac.Message = fmt.Sprintf("The Slice %q is not operational due to an error: %s", slice.Name, errCond.Message)
	}

	err := r.updateWorkloadAdmissionCheckStatus(ctx, wl, ac)
	if err == nil && originalState != ac.State {
		message := fmt.Sprintf("Admission check %q updated state from %q to %q", ac.Name, originalState, ac.State)
		r.record.Event(wl, corev1.EventTypeNormal, AdmissionCheckUpdatedEventType, message)
	}

	return err
}

// SetupWithManager sets up the controller with the Manager.
func (r *WorkloadReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&kueue.Workload{}).
		Named("workload_controller").
		WithEventFilter(r).
		Watches(&v1alpha1.Slice{}, &sliceHandler{client: r.client}).
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
	if controllerutil.ContainsFinalizer(wl, SliceControllerName) {
		return true
	}
	finalize, _ := shouldFinalize(wl)
	// If the Workload doesn’t have a finalizer, we can handle only relevant workloads.
	return !finalize && validateRelevantWorkload(wl) == nil
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
	// No need to handle create event. We should wait for at least Forming state.
}

func (h *sliceHandler) Delete(ctx context.Context, e event.DeleteEvent, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	h.handleEvent(ctx, e.Object, q)
}

func (h *sliceHandler) Update(ctx context.Context, e event.UpdateEvent, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	h.handleEvent(ctx, e.ObjectNew, q)
}

func (h *sliceHandler) handleEvent(ctx context.Context, obj client.Object, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	slice, isSlice := obj.(*v1alpha1.Slice)
	// Only Slice should be handled.
	if !isSlice {
		return
	}

	log := ctrl.LoggerFrom(ctx)

	owner := metav1.GetControllerOf(slice)
	if owner == nil {
		log.V(3).Info("Owner not found")
		return
	}

	log.V(3).Info("Handle Slice event", "workload", klog.KRef(slice.Namespace, slice.Name))

	req := reconcile.Request{
		NamespacedName: types.NamespacedName{
			Name:      owner.Name,
			Namespace: slice.Namespace,
		},
	}

	q.AddAfter(req, updatesBatchPeriod)
}
