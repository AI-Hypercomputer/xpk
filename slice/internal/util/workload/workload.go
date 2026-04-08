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

package workload

import (
	batchv1 "k8s.io/api/batch/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta2"
	kueueworkload "sigs.k8s.io/kueue/pkg/workload"
	leaderworkersetv1 "sigs.k8s.io/lws/api/leaderworkerset/v1"
)

func ShouldFinalize(wl *kueue.Workload) (bool, string) {
	if !wl.DeletionTimestamp.IsZero() {
		return true, "it has been deleted"
	}
	if kueueworkload.IsFinished(wl) {
		return true, "it has finished"
	}
	if kueueworkload.IsEvicted(wl) {
		return true, "it was evicted"
	}
	if !kueueworkload.IsActive(wl) {
		return true, "it is no longer active"
	}
	if GetOwner(wl) == nil {
		return true, "it doesn't have owner"
	}
	if !HasSupportedOwner(wl) {
		return true, "it has an unsupported owner"
	}
	return false, ""
}

func HasSupportedOwner(wl *kueue.Workload) bool {
	return IsJobSetOwner(wl) || IsJobOwner(wl) || IsLeaderWorkerSetOwner(wl)
}

func IsJobSetOwner(wl *kueue.Workload) bool {
	if owner := metav1.GetControllerOf(wl); owner != nil {
		return owner.APIVersion == jobset.SchemeGroupVersion.String() && owner.Kind == "JobSet"
	}
	return false
}

func IsJobOwner(wl *kueue.Workload) bool {
	if owner := metav1.GetControllerOf(wl); owner != nil {
		return owner.APIVersion == batchv1.SchemeGroupVersion.String() && owner.Kind == "Job"
	}
	return false
}

func IsLeaderWorkerSetOwner(wl *kueue.Workload) bool {
	if owner := GetOwner(wl); owner != nil {
		return owner.APIVersion == leaderworkersetv1.SchemeGroupVersion.String() && owner.Kind == "LeaderWorkerSet"
	}
	return false
}

func GetOwner(wl *kueue.Workload) *metav1.OwnerReference {
	if owner := metav1.GetControllerOf(wl); owner != nil {
		return owner
	}
	for i := range wl.OwnerReferences {
		owner := &wl.OwnerReferences[i]
		if owner.Kind == "JobSet" || owner.Kind == "Job" || owner.Kind == "LeaderWorkerSet" {
			return owner
		}
	}
	return nil
}
