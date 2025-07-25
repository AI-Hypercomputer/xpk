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
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	"sigs.k8s.io/kueue/pkg/util/admissioncheck"
	"sigs.k8s.io/kueue/pkg/workload"

	"tpu-slice-controller/api/v1alpha1"
	"tpu-slice-controller/internal/util/api"
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

func (r *WorkloadReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	wl := &kueue.Workload{}
	err := r.client.Get(ctx, req.NamespacedName, wl)
	if err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	log := ctrl.LoggerFrom(ctx)
	log.V(2).Info("Reconcile Workload")

	if r.shouldFinalize(wl) {
		if controllerutil.ContainsFinalizer(wl, SliceControllerName) {
			err = r.client.Delete(ctx, r.newEmptySlice(wl))
			if client.IgnoreNotFound(err) != nil {
				return ctrl.Result{}, err
			}
			controllerutil.RemoveFinalizer(wl, SliceControllerName)
			if err := r.client.Update(ctx, wl); err != nil {
				if !apierrors.IsNotFound(err) {
					log.Error(err, "Failed to remove finalizer")
				}
				return ctrl.Result{}, client.IgnoreNotFound(err)
			}
			log.V(5).Info("Removed finalizer")
		}
		return ctrl.Result{}, nil
	}

	if controllerutil.AddFinalizer(wl, SliceControllerName) {
		if err = r.client.Update(ctx, wl); err != nil {
			if !apierrors.IsNotFound(err) {
				log.Error(err, "Failed to add finalizer")
			}
			return ctrl.Result{}, client.IgnoreNotFound(err)
		}
		log.V(5).Info("Added finalizer")
		return ctrl.Result{}, nil
	}

	ac, err := r.sliceAC(ctx, wl)
	if err != nil {
		return reconcile.Result{}, err
	}
	if ac == nil {
		log.V(5).Info("Admission check not found – ignoring reconciliation for now")
		return reconcile.Result{}, nil
	}

	log = log.WithValues("admissionCheck", ac.Name)
	ctrl.LoggerInto(ctx, log)

	if ac.State == kueue.CheckStateReady {
		log.V(5).Info("Admission check is ready — nothing to do")
		return reconcile.Result{}, nil
	}

	slice := r.newEmptySlice(wl)

	err = r.client.Get(ctx, client.ObjectKeyFromObject(slice), slice)
	if client.IgnoreNotFound(err) != nil {
		log.Error(err, "Failed to fetch the Slice")
		return ctrl.Result{}, err
	}
	if err != nil {
		return ctrl.Result{}, r.createSlice(ctx, wl, ac)
	}

	return ctrl.Result{}, client.IgnoreNotFound(r.syncAdmissionCheckStatus(ctx, wl, ac, slice))
}

func (r *WorkloadReconciler) shouldFinalize(wl *kueue.Workload) bool {
	return !wl.DeletionTimestamp.IsZero() || workload.IsFinished(wl) || workload.IsEvicted(wl) || !workload.IsActive(wl)
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
	if wl.Status.Admission == nil || wl.Status.Admission.PodSetAssignments == nil {
		return slice, nil
	}

	nodeSelectors := sets.New[string]()
	for _, psa := range wl.Status.Admission.PodSetAssignments {
		for _, domain := range psa.TopologyAssignment.Domains {
			nodeSelectors.Insert(domain.Values...)
		}
	}
	slice.Spec.NodeSelector = map[string][]string{
		TPUReservationSubblockLabel: sets.List(nodeSelectors),
	}
	return slice, nil
}

func (r *WorkloadReconciler) createSlice(ctx context.Context, wl *kueue.Workload, ac *kueue.AdmissionCheckState) error {
	slice, err := r.newSlice(wl)
	if err != nil {
		return err
	}

	log := ctrl.LoggerFrom(ctx).WithValues("slice", klog.KObj(slice))

	err = r.client.Create(ctx, slice)
	if err != nil {
		msg := fmt.Sprintf("Error creating Slice %q: %v", slice.Name, err)
		log.Error(err, msg)
		r.record.Event(wl, corev1.EventTypeWarning, FailedCreateSliceEventType, api.TruncateEventMessage(msg))
		ac.Message = api.TruncateConditionMessage(msg)
		patchErr := r.updateWorkloadAdmissionCheckStatus(ctx, wl, ac)
		return errors.Join(err, patchErr)
	}

	msg := fmt.Sprintf("The Slice %q has been created", slice.Name)
	log.V(5).Info(msg)
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
	case meta.IsStatusConditionTrue(slice.Status.Conditions, string(v1alpha1.Forming)):
		ac.Message = fmt.Sprintf("The Slice %q is being formed", slice.Name)
	case meta.IsStatusConditionTrue(slice.Status.Conditions, string(v1alpha1.Ready)):
		ac.State = kueue.CheckStateReady
		ac.Message = fmt.Sprintf("The Slice %q is fully operational", slice.Name)
	case meta.IsStatusConditionTrue(slice.Status.Conditions, string(v1alpha1.Degraded)):
		ac.State = kueue.CheckStateReady
		ac.Message = fmt.Sprintf("The Slice %q is running with reduced capacity or performance", slice.Name)
	case meta.IsStatusConditionTrue(slice.Status.Conditions, string(v1alpha1.Deformed)):
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
		Watches(&v1alpha1.Slice{}, &sliceHandler{client: r.client}).
		Complete(r)
}

var _ handler.EventHandler = (*sliceHandler)(nil)

type sliceHandler struct {
	client client.Client
}

func (h *sliceHandler) Generic(context.Context, event.GenericEvent, workqueue.TypedRateLimitingInterface[reconcile.Request]) {
}

func (h *sliceHandler) Create(ctx context.Context, e event.CreateEvent, q workqueue.TypedRateLimitingInterface[reconcile.Request]) {
	h.handleEvent(ctx, e.Object, q)
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
