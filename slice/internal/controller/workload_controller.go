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
	"k8s.io/utils/ptr"
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

	"tpu-slice-controller/api/v1beta1"
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
	updatesBatchPeriod       = time.Second
	cleanupRetryAfter        = 5 * time.Second
	initializationRetryAfter = 5 * time.Second
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
// +kubebuilder:rbac:groups=accelerator.gke.io,resources=slices,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=accelerator.gke.io,resources=slices/finalizers,verbs=update
// +kubebuilder:rbac:groups="",resources=events,verbs=create;watch;update;patch
// +kubebuilder:rbac:groups=jobset.x-k8s.io,resources=jobsets,verbs=get;list;watch;update
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

	grouped := r.groupSlices(slices)
	if len(grouped.deleted) > 0 {
		log.V(3).Info(
			"Waiting for deleted Slices to be cleaned up; skipping reconciliation for now",
			"deletedSlices", klog.KObjSlice(grouped.deleted),
		)
		return ctrl.Result{}, err
	}

	newSlices, err := r.syncSlices(ctx, wl, ac, slices, nodes)
	if err != nil {
		return ctrl.Result{}, err
	}
	if len(newSlices) > 0 {
		slices = append(slices, newSlices...)
		// Re-group the slices to include the newly created ones.
		grouped = r.groupSlices(slices)
	}

	if len(grouped.active) == len(slices) && len(slices) > 0 {
		log.V(3).Info("Annotating owner before unsuspending")
		err := r.updateOwnerBeforeUnsuspend(ctx, wl)
		if err != nil {
			return ctrl.Result{}, err
		}
	}

	err = r.syncAdmissionCheckStatus(ctx, wl, ac, slices)
	if err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	if len(grouped.toDelete) > 0 {
		log.V(3).Info(
			"Deleting Slices",
			"slices", klog.KObjSlice(grouped.toDelete),
		)
		err = r.deleteSlices(ctx, grouped.toDelete)
		if err != nil {
			return ctrl.Result{}, err
		}
	}
	if len(grouped.initializing) > 0 {
		log.V(3).Info(
			"Waiting for Slices to be initialized",
			"slices", klog.KObjSlice(grouped.initializing),
		)
		return ctrl.Result{RequeueAfter: initializationRetryAfter}, nil
	}
	return ctrl.Result{}, nil
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
	mapNodes := make(map[string]corev1.Node, len(nodes.Items))
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

	grouped := r.groupSlices(slices)

	if len(grouped.deleted) == len(slices) {
		log.V(3).Info("All slices already deleted; finishing cleanup")
		return true, nil
	}

	if len(grouped.active)+len(grouped.toDelete)+len(grouped.initializing) > 0 {
		terminated, err := r.ownerPodsFinished(ctx, wl)
		if err != nil || !terminated {
			return false, err
		}
	}
	// after pods are terminated we should cleanup all the slices (including active and initializing ones)
	toDelete := append(grouped.toDelete, grouped.active...)
	toDelete = append(toDelete, grouped.initializing...)
	log.V(3).Info("Deleting Slices", "slices", klog.KObjSlice(toDelete))
	err = r.deleteSlices(ctx, toDelete)
	if err != nil {
		return false, err
	}

	return true, nil
}

func (r *WorkloadReconciler) findWorkloadSlices(ctx context.Context, wl *kueue.Workload) ([]v1beta1.Slice, error) {
	slices := &v1beta1.SliceList{}
	opts := []client.ListOption{
		client.MatchingFields{
			WorkloadNamespaceIndex: wl.Namespace,
			WorkloadNameIndex:      wl.Name,
		},
	}
	if err := r.client.List(ctx, slices, opts...); err != nil {
		return nil, err
	}
	return slices.Items, nil
}

type groupedSlices struct {
	deleted      []v1beta1.Slice
	toDelete     []v1beta1.Slice
	initializing []v1beta1.Slice
	active       []v1beta1.Slice
}

// groupSlices categorizes a list of Slice objects into four groups based on their state.
// It separates slices into deleted (marked for deletion), ones that should be delete
// (errored and stale), ones that are initializning, and other (active) slices.
//
// Parameters:
//
//	slices - A slice of v1beta1.Slice objects to be categorized.
//
// Returns:
//
//	A groupedSlices struct containing categorized slices.
func (r *WorkloadReconciler) groupSlices(slices []v1beta1.Slice) groupedSlices {
	gs := groupedSlices{}
	for _, slice := range slices {
		switch core.GetSliceState(slice) {
		case core.SliceStateDeleted:
			gs.deleted = append(gs.deleted, slice)
		case core.SliceStateFailed, core.SliceStateStale:
			gs.toDelete = append(gs.toDelete, slice)
		case core.SliceStateCreated, core.SliceStateActivating:
			gs.initializing = append(gs.initializing, slice)
		case core.SliceStateActive, core.SliceStateActiveDegraded:
			gs.active = append(gs.active, slice)
		}
	}
	return gs
}

func (r *WorkloadReconciler) deleteSlices(ctx context.Context, slices []v1beta1.Slice) error {
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

func (r *WorkloadReconciler) updateOwnerBeforeUnsuspend(ctx context.Context, wl *kueue.Workload) error {
	// For now, we only support JobSets.
	if isJobSetOwner(wl) {
		return r.updateJobSetBeforeUnsuspend(ctx, wl)
	}
	return nil
}

func (r *WorkloadReconciler) updateJobSetBeforeUnsuspend(ctx context.Context, wl *kueue.Workload) error {
	owner := metav1.GetControllerOf(wl)
	log := ctrl.LoggerFrom(ctx).WithValues("jobSet", klog.KRef(wl.Namespace, owner.Name))
	jobSet := &jobset.JobSet{}
	jobSetKey := types.NamespacedName{Name: owner.Name, Namespace: wl.Namespace}
	if err := r.client.Get(ctx, jobSetKey, jobSet); err != nil {
		log.Error(err, "Failed to get JobSet")
		return err
	}
	for i := range jobSet.Spec.ReplicatedJobs {
		rj := &jobSet.Spec.ReplicatedJobs[i]
		topology := rj.Template.Spec.Template.Annotations[core.TPUSliceTopologyAnnotation]
		log.V(5).Info("Copying topology annotation as nodeSelector", "topology", topology)
		if rj.Template.Spec.Template.Spec.NodeSelector == nil {
			rj.Template.Spec.Template.Spec.NodeSelector = make(map[string]string)
		}
		rj.Template.Spec.Template.Spec.NodeSelector[core.TPUTopologyAnnotation] = topology
	}
	if err := r.client.Update(ctx, jobSet); err != nil {
		log.Error(err, "Failed to update JobSet")
		return err
	}
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
	return admissioncheck.FindAdmissionCheck(wl.Status.AdmissionChecks, relevantChecks[0]), nil
}

func (r *WorkloadReconciler) syncSlices(
	ctx context.Context,
	wl *kueue.Workload,
	ac *kueue.AdmissionCheckState,
	slices []v1beta1.Slice,
	nodes map[string]corev1.Node,
) ([]v1beta1.Slice, error) {
	existingSlicesByName := make(map[string]*v1beta1.Slice, len(slices))
	for _, slice := range slices {
		existingSlicesByName[slice.Name] = &slice
	}

	allCreatedSlices := make([]v1beta1.Slice, 0, len(wl.Status.Admission.PodSetAssignments))
	for _, psa := range wl.Status.Admission.PodSetAssignments {
		if !shouldCreateSlicesForPodSetAssignment(wl, psa, nodes) {
			continue
		}
		ps := podset.FindPodSetByName(wl.Spec.PodSets, psa.Name)
		if ps.TopologyRequest == nil {
			continue
		}
		desiredNumberOfSlices := ptr.Deref(ps.TopologyRequest.SubGroupCount, 1)

		createdSlices, err := r.createSlices(ctx, wl, ac, &psa, nodes, existingSlicesByName, desiredNumberOfSlices)
		if err != nil {
			return allCreatedSlices, err
		}
		allCreatedSlices = append(allCreatedSlices, createdSlices...)
	}

	if len(allCreatedSlices) > 0 {
		msg := buildCreationEventMessage(allCreatedSlices)
		ctrl.LoggerFrom(ctx).V(3).Info(msg)
		r.record.Event(wl, corev1.EventTypeNormal, SlicesCreatedEventType, api.TruncateEventMessage(msg))
	}

	return allCreatedSlices, nil
}

func shouldCreateSlicesForPodSetAssignment(wl *kueue.Workload, psa kueue.PodSetAssignment, nodes map[string]corev1.Node) bool {
	if podSet := podset.FindPodSetByName(wl.Spec.PodSets, psa.Name); podSet != nil {
		return core.IsRelevantPodTemplateSpec(podSet.Template) && topology.IsAssignmentValid(psa, nodes)
	}
	return false
}

func parseTopologyAssignment(topologyAssignment *kueue.TopologyAssignment, nodes map[string]corev1.Node) []string {
	var subBlockIds []string
	seenSubBlockIds := sets.New[string]()
	// we already validated that all assignments have a valid level,
	// in validateRelevantWorkload.
	hostnameLevelIndex := topology.HostnameLevelIndex(topologyAssignment)
	for _, domain := range topologyAssignment.Domains {
		nodeName := domain.Values[hostnameLevelIndex]
		if subBlockId := topology.GetTPUSubBlockLabelValue(nodes, nodeName); !seenSubBlockIds.Has(subBlockId) {
			subBlockIds = append(subBlockIds, subBlockId)
			seenSubBlockIds.Insert(subBlockId)
		}
	}
	return subBlockIds
}

func (r *WorkloadReconciler) createSlices(ctx context.Context, wl *kueue.Workload, ac *kueue.AdmissionCheckState, psa *kueue.PodSetAssignment, nodes map[string]corev1.Node, existingSlicesByName map[string]*v1beta1.Slice, desiredNumberOfSlices int32) ([]v1beta1.Slice, error) {
	partitionIDs := parseTopologyAssignment(psa.TopologyAssignment, nodes)
	ps := podset.FindPodSetByName(wl.Spec.PodSets, psa.Name)
	chunkSize := int32(len(partitionIDs) / int(desiredNumberOfSlices))
	createdSlices := []v1beta1.Slice{}
	for i := int32(0); i < desiredNumberOfSlices; i++ {
		if _, exist := existingSlicesByName[core.SliceName(wl.Namespace, wl.Name, psa.Name, i)]; exist {
			// Slice already exists, nothing to do.
			continue
		}
		slice := core.SliceWithMetadata(wl, psa.Name, i)
		log := ctrl.LoggerFrom(ctx).WithValues("slice", klog.KObj(slice))
		log.V(3).Info("Creating Slice")
		// Since Slice is a cluster-scoped object and Workload is namespaced,
		// we cannot set a controller owner reference. The Workload's namespace and name
		// are stored as annotations on the Slice for lookup.

		slice.Spec.Type = v1beta1.Type(core.GetTPUAccelerator(ps.Template))
		start := i * chunkSize
		end := start + chunkSize
		if len(partitionIDs) > 0 {
			slice.Spec.PartitionIds = partitionIDs[start:end]
		}

		slice.Spec.Topology = core.GetTPUTopology(ps.Template)

		if err := r.client.Create(ctx, slice); err != nil {
			msg := fmt.Sprintf("Error creating Slice %q: %v", slice.Name, err)
			log.Error(err, msg)
			r.record.Event(wl, corev1.EventTypeWarning, FailedCreateSliceEventType, api.TruncateEventMessage(msg))
			ac.State = kueue.CheckStatePending
			ac.Message = api.TruncateConditionMessage(msg)
			patchErr := r.updateWorkloadAdmissionCheckStatus(ctx, wl, ac)
			return nil, errors.Join(err, patchErr)
		}
		createdSlices = append(createdSlices, *slice)
	}
	return createdSlices, nil
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

func buildCreationEventMessage(slices []v1beta1.Slice) string {
	sliceNames := make([]string, len(slices))
	for index, slice := range slices {
		sliceNames[index] = fmt.Sprintf("%q", slice.Name)
	}
	sort.Strings(sliceNames)
	return fmt.Sprintf("The Slices %s have been created", strings.Join(sliceNames, ", "))
}

// syncAdmissionCheckStatus syncs the admission check status with the state of the Slices.
func (r *WorkloadReconciler) syncAdmissionCheckStatus(ctx context.Context, wl *kueue.Workload, ac *kueue.AdmissionCheckState, slices []v1beta1.Slice) error {
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
			cond := meta.FindStatusCondition(slice.Status.Conditions, v1beta1.SliceStateConditionType)
			if cond != nil && cond.Status == metav1.ConditionFalse && cond.Reason == string(core.MMIGHealthStatusFailed) {
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

func groupSlicesByState(slices []v1beta1.Slice) map[core.SliceState][]v1beta1.Slice {
	slicesByState := make(map[core.SliceState][]v1beta1.Slice)
	for _, slice := range slices {
		slicesByState[core.GetSliceState(slice)] = append(slicesByState[core.GetSliceState(slice)], slice)
	}
	return slicesByState
}

func prepareAdmissionCheckStatus(ac *kueue.AdmissionCheckState, slices []v1beta1.Slice) {
	slicesByState := groupSlicesByState(slices)

	switch {
	case len(slices) == len(slicesByState[core.SliceStateActive])+len(slicesByState[core.SliceStateActiveDegraded]):
		ac.State = kueue.CheckStateReady
	case len(slicesByState[core.SliceStateFailed]) > 0:
		ac.State = kueue.CheckStateRetry
	case len(slicesByState[core.SliceStateCreated])+len(slicesByState[core.SliceStateActivating]) > 0:
		ac.State = kueue.CheckStatePending
	}

	var stateMessages []string
	for _, state := range core.SliceStates {
		if count := len(slicesByState[state]); count > 0 {
			stateMessages = append(stateMessages, fmt.Sprintf("%d %s", count, state))
		}
	}

	ac.Message = fmt.Sprintf("Slices are in states: %s", strings.Join(stateMessages, ", "))

	if len(slicesByState[core.SliceStateFailed]) > 0 {
		var errMessages []string
		for _, slice := range slicesByState[core.SliceStateFailed] {
			cond := meta.FindStatusCondition(slice.Status.Conditions, v1beta1.SliceStateConditionType)
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
		Watches(&v1beta1.Slice{}, &sliceHandler{client: r.client}).
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
	slice, isSlice := obj.(*v1beta1.Slice)
	// Only Slice should be handled.
	if !isSlice {
		return
	}

	log := ctrl.LoggerFrom(ctx)

	workloadNamespace, nsFound := slice.Annotations[core.OwnerWorkloadNamespaceAnnotation]
	workloadName, nameFound := slice.Annotations[core.OwnerWorkloadNameAnnotation]

	if !nsFound || !nameFound {
		log.V(3).Info("Slice is missing workload owner annotations, skipping event handling", "slice", klog.KObj(slice))
		return
	}

	log.V(3).Info("Handle Slice event", "workload", klog.KRef(workloadNamespace, workloadName))

	req := reconcile.Request{
		NamespacedName: types.NamespacedName{
			Name:      workloadName,
			Namespace: workloadNamespace,
		},
	}

	q.AddAfter(req, updatesBatchPeriod)
}
