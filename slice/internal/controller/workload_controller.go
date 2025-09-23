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
	"sort"
	"strings"
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
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	"sigs.k8s.io/kueue/pkg/util/admissioncheck"
	"sigs.k8s.io/kueue/pkg/util/podset"
	"sigs.k8s.io/kueue/pkg/workload"

	"tpu-slice-controller/api/v1alpha1"
	"tpu-slice-controller/internal/core"
	"tpu-slice-controller/internal/topology"
	"tpu-slice-controller/internal/util/api"
	utilpod "tpu-slice-controller/internal/util/pod"
)

const (
	SliceControllerName = "accelerator.gke.io/slice"

	SlicesCreatedEventType         = "SlicesCreated"
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

// +kubebuilder:rbac:groups="",resources=nodes,verbs=get;list;watch
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
		if controllerutil.ContainsFinalizer(wl, SliceControllerName) {
			log.V(3).Info(fmt.Sprintf("Cleaning up the Slices and finalizing the Workload because %s", reason))
			cleanedUp, err := r.cleanupSlices(ctx, wl)
			if err != nil {
				return ctrl.Result{}, err
			}
			if !cleanedUp {
				return ctrl.Result{RequeueAfter: cleanupRetryAfter}, nil
			}
			err = r.finalizeWorkload(ctx, wl)
			return ctrl.Result{}, client.IgnoreNotFound(err)
		}
		return ctrl.Result{}, nil
	}

	nodes, err := r.getNodes(ctx)
	if err != nil {
		return ctrl.Result{}, err
	}

	if err = validateRelevantWorkload(wl, nodes); err != nil {
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

	slices, err := r.findWorkloadSlices(ctx, wl)
	if err != nil {
		log.Error(err, "Failed to list Slices")
		return ctrl.Result{}, err
	}

	deleted, _, _ := r.groupSlices(slices)
	if len(deleted) > 0 {
		log.V(3).Info(
			"Waiting for deleted Slices to be cleaned up; skipping reconciliation for now",
			"deletedSlices", klog.KObjSlice(deleted),
		)
		return ctrl.Result{}, err
	}

	err = r.syncSlices(ctx, wl, ac, &slices, nodes)
	if err != nil {
		return ctrl.Result{}, err
	}

	err = r.syncAdmissionCheckStatus(ctx, wl, ac, slices)
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

func (r *WorkloadReconciler) getNodes(ctx context.Context) (map[string]corev1.Node, error) {
	nodes := &corev1.NodeList{}
	err := r.client.List(ctx, nodes)
	if err != nil {
		return nil, err
	}
	mapNodes := make(map[string]corev1.Node)
	for _, node := range nodes.Items {
		mapNodes[node.Name] = node
	}
	return mapNodes, nil
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

func (r *WorkloadReconciler) cleanupSlices(ctx context.Context, wl *kueue.Workload) (bool, error) {
	log := ctrl.LoggerFrom(ctx)

	slices, err := r.findWorkloadSlices(ctx, wl)
	if err != nil {
		log.Error(err, "Failed to fetch Slices")
		return false, err
	}

	deleted, deformed, other := r.groupSlices(slices)

	if len(deleted) == len(slices) {
		log.V(3).Info("All slices already deleted; finishing cleanup")
		return true, nil
	}

	if len(deformed) > 0 {
		log.V(3).Info("Found Slices in deformed state; cleaning them up", "deformedSlices", klog.KObjSlice(deformed))
		// We still need to delete deformed Slices because requeueing causes a conflict error during Slice creation.
		err = r.deleteSlices(ctx, deformed)
		if err != nil {
			return false, err
		}
	}

	if len(other) > 0 {
		terminated, err := r.ownerPodsFinished(ctx, wl)
		if err != nil || !terminated {
			return false, err
		}
	}

	log.V(3).Info("Deleting Slices", "slices", klog.KObjSlice(other))
	err = r.deleteSlices(ctx, other)
	if err != nil {
		return false, err
	}

	return true, nil
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

// groupSlices categorizes a list of Slice objects into three groups based on their state.
// It separates slices into deleted (marked for deletion), deformed (being torn down),
// and other (active) slices.
//
// Parameters:
//
//	slices - A slice of v1alpha1.Slice objects to be categorized.
//
// Returns:
//   - A slice containing deleted Slice objects (with non-zero DeletionTimestamp).
//   - A slice containing deformed Slice objects (being torn down).
//   - A slice containing other Slice objects (active/valid slices).
func (r *WorkloadReconciler) groupSlices(slices []v1alpha1.Slice) ([]v1alpha1.Slice, []v1alpha1.Slice, []v1alpha1.Slice) {
	var deleted, deformed, other []v1alpha1.Slice
	for _, slice := range slices {
		switch {
		case !slice.DeletionTimestamp.IsZero():
			deleted = append(deleted, slice)
		case core.Deformed(&slice):
			deformed = append(deformed, slice)
		default:
			other = append(other, slice)
		}
	}
	return deleted, deformed, other
}

func (r *WorkloadReconciler) deleteSlices(ctx context.Context, slices []v1alpha1.Slice) error {
	log := ctrl.LoggerFrom(ctx)
	for _, slice := range slices {
		log = log.WithValues("slice", klog.KObj(&slice))
		log.V(3).Info("Deleting the Slice")
		err := r.client.Delete(ctx, &slice)
		if client.IgnoreNotFound(err) != nil {
			log.Error(err, "Failed to delete the Slice")
			return err
		}
	}
	return nil
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

func validateRelevantWorkload(wl *kueue.Workload, nodes map[string]corev1.Node) error {
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
	if !topology.AllAssignmentsValid(wl.Status.Admission, nodes) {
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

func (r *WorkloadReconciler) syncSlices(
	ctx context.Context,
	wl *kueue.Workload,
	ac *kueue.AdmissionCheckState,
	slices *[]v1alpha1.Slice,
	nodes map[string]corev1.Node,
) error {
	slicesByName := make(map[string]*v1alpha1.Slice, len(*slices))
	for _, slice := range *slices {
		slicesByName[slice.Name] = &slice
	}

	createdSlices := make([]v1alpha1.Slice, 0, len(wl.Status.Admission.PodSetAssignments))
	for _, psa := range wl.Status.Admission.PodSetAssignments {
		if !shouldCreateSliceForPodSetAssignment(wl, psa, nodes) {
			continue
		}

		sliceName := core.SliceName(wl.Name, psa.Name)

		if _, exist := slicesByName[sliceName]; exist {
			// Slice already exists, nothing to do.
			continue
		}

		createdSlice, err := r.createSlice(ctx, wl, ac, &psa, nodes)
		if err != nil {
			return err
		}

		*slices = append(*slices, *createdSlice)
		createdSlices = append(createdSlices, *createdSlice)
	}

	if len(createdSlices) > 0 {
		msg := buildCreationEventMessage(createdSlices)
		ctrl.LoggerFrom(ctx).V(3).Info(msg)
		r.record.Event(wl, corev1.EventTypeNormal, SlicesCreatedEventType, api.TruncateEventMessage(msg))
	}

	return nil
}

func shouldCreateSliceForPodSetAssignment(wl *kueue.Workload, psa kueue.PodSetAssignment, nodes map[string]corev1.Node) bool {
	if podSet := podset.FindPodSetByName(wl.Spec.PodSets, psa.Name); podSet != nil {
		return core.IsRelevantPodTemplateSpec(podSet.Template) && topology.IsAssignmentValid(psa, nodes)
	}
	return false
}

func parseTopologyAssignmentIntoNodeSelector(slice *v1alpha1.Slice, topologyAssignment *kueue.TopologyAssignment, nodes map[string]corev1.Node) {
	nodeSelectors := sets.New[string]()
	// we already validated that all assignments have a valid level,
	// in validateRelevantWorkload.
	if subblockLevelIndex := topology.LevelIndex(topologyAssignment, core.TPUSubBlockLabel); subblockLevelIndex != -1 {
		for _, domain := range topologyAssignment.Domains {
			nodeSelectors.Insert(domain.Values[subblockLevelIndex])
		}
	} else if hostnameLevelIndex := topology.LevelIndex(topologyAssignment, corev1.LabelHostname); hostnameLevelIndex != -1 {
		for _, domain := range topologyAssignment.Domains {
			nodeSelectors.Insert(topology.GetTPUSubBlockLabelValue(domain, hostnameLevelIndex, nodes))
		}
	}
	// In the future, we want to make sure nodeSelectorKey
	// matches PodSetSliceRequiredTopologyAnnotation.
	nodeSelectorKey := core.TPUSubBlockLabel
	slice.Spec.NodeSelector = map[string][]string{
		nodeSelectorKey: sets.List(nodeSelectors),
	}
}

func (r *WorkloadReconciler) createSlice(ctx context.Context, wl *kueue.Workload, ac *kueue.AdmissionCheckState, psa *kueue.PodSetAssignment, nodes map[string]corev1.Node) (*v1alpha1.Slice, error) {
	slice := core.SliceWithMetadata(wl, psa.Name)
	log := ctrl.LoggerFrom(ctx).WithValues("slice", klog.KObj(slice))
	log.V(3).Info("Creating Slice")

	if err := controllerutil.SetControllerReference(wl, slice, r.client.Scheme()); err != nil {
		return nil, err
	}
	parseTopologyAssignmentIntoNodeSelector(slice, psa.TopologyAssignment, nodes)

	if err := r.client.Create(ctx, slice); err != nil {
		msg := fmt.Sprintf("Error creating Slice %q: %v", client.ObjectKeyFromObject(slice), err)
		log.Error(err, msg)
		r.record.Event(wl, corev1.EventTypeWarning, FailedCreateSliceEventType, api.TruncateEventMessage(msg))
		ac.State = kueue.CheckStatePending
		ac.Message = api.TruncateConditionMessage(msg)
		patchErr := r.updateWorkloadAdmissionCheckStatus(ctx, wl, ac)
		return nil, errors.Join(err, patchErr)
	}

	return slice, nil
}

func (r *WorkloadReconciler) updateWorkloadAdmissionCheckStatus(ctx context.Context, wl *kueue.Workload, ac *kueue.AdmissionCheckState) error {
	wlPatch := workload.BaseSSAWorkload(wl, true)
	workload.SetAdmissionCheckState(&wlPatch.Status.AdmissionChecks, *ac, r.clock)
	err := r.client.Status().Patch(ctx, wlPatch, client.Apply, client.FieldOwner(SliceControllerName), client.ForceOwnership)
	if err != nil && !apierrors.IsNotFound(err) {
		ctrl.LoggerFrom(ctx).Error(err, "Failed to patch the Workload's admission status")
	}
	return err
}

func buildCreationEventMessage(slices []v1alpha1.Slice) string {
	sliceNames := make([]string, len(slices))
	for index, slice := range slices {
		sliceNames[index] = fmt.Sprintf("%q", client.ObjectKeyFromObject(&slice))
	}
	sort.Strings(sliceNames)
	return fmt.Sprintf("The Slices %s have been created", strings.Join(sliceNames, ", "))
}

// syncAdmissionCheckStatus syncs the admission check status with the state of the Slices.
func (r *WorkloadReconciler) syncAdmissionCheckStatus(ctx context.Context, wl *kueue.Workload, ac *kueue.AdmissionCheckState, slices []v1alpha1.Slice) error {
	originalState := ac.State
	originalMessage := ac.Message

	prepareAdmissionCheckStatus(ac, slices)

	// No changes.
	if originalState == ac.State && ac.Message == originalMessage {
		return nil
	}

	if err := r.updateWorkloadAdmissionCheckStatus(ctx, wl, ac); err != nil {
		return err
	}

	log := ctrl.LoggerFrom(ctx)

	if originalState != ac.State {
		message := fmt.Sprintf("Admission check %q updated state from %q to %q", ac.Name, originalState, ac.State)
		log.V(3).Info(message)
		r.record.Event(wl, corev1.EventTypeNormal, AdmissionCheckUpdatedEventType, message)
	}

	if ac.Message != originalMessage {
		// Logging error messages if exists
		for _, slice := range slices {
			cond := meta.FindStatusCondition(slice.Status.Conditions, string(v1alpha1.Error))
			if cond != nil && cond.Status == metav1.ConditionTrue {
				log.V(2).Info(
					"WARNING: The Slice is not operational due to an error",
					"slice", klog.KObj(&slice),
					"error", cond.Message,
				)
			}
		}
	}

	return nil
}

func groupSlicesByState(slices []v1alpha1.Slice) (map[v1alpha1.SliceConditionType][]v1alpha1.Slice, []v1alpha1.Slice) {
	slicesByState := make(map[v1alpha1.SliceConditionType][]v1alpha1.Slice)
	var noState []v1alpha1.Slice
	for _, slice := range slices {
		foundState := false
		for _, status := range core.SliceStates {
			if meta.IsStatusConditionTrue(slice.Status.Conditions, string(status)) {
				slicesByState[status] = append(slicesByState[status], slice)
				foundState = true
				break
			}
		}
		if !foundState {
			noState = append(noState, slice)
		}
	}
	return slicesByState, noState
}

func prepareAdmissionCheckStatus(ac *kueue.AdmissionCheckState, slices []v1alpha1.Slice) {
	slicesByState, noState := groupSlicesByState(slices)

	switch {
	case len(slicesByState[v1alpha1.Error]) > 0 || len(slicesByState[v1alpha1.Deformed]) > 0:
		ac.State = kueue.CheckStateRejected
	case len(slices) == len(slicesByState[v1alpha1.Degraded])+len(slicesByState[v1alpha1.Ready]):
		ac.State = kueue.CheckStateReady
	}

	var stateMessages []string
	if len(noState) > 0 {
		stateMessages = append(stateMessages, fmt.Sprintf("%d Created", len(noState)))
	}

	for _, state := range core.SliceStates {
		if count := len(slicesByState[state]); count > 0 {
			stateMessages = append(stateMessages, fmt.Sprintf("%d %s", count, state))
		}
	}

	ac.Message = fmt.Sprintf("Slices are in states: %s", strings.Join(stateMessages, ", "))

	if len(slicesByState[v1alpha1.Error]) > 0 {
		var errMessages []string
		for _, slice := range slicesByState[v1alpha1.Error] {
			cond := meta.FindStatusCondition(slice.Status.Conditions, string(v1alpha1.Error))
			errMessages = append(errMessages, cond.Message)
		}
		ac.Message += ". Errors: " + strings.Join(errMessages, "; ")
	}
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
