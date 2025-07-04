// Copyright The Kubernetes Authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package core

import (
	"fmt"

	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	"tpu-slice-controller/api/v1alpha1"
)

var SliceStatuses = []v1alpha1.SliceConditionType{
	v1alpha1.Error, v1alpha1.Deformed, v1alpha1.Forming, v1alpha1.Degraded, v1alpha1.Ready,
}

func SliceKeyFromWorkload(wl *kueue.Workload, podSetName kueue.PodSetReference) client.ObjectKey {
	slice := SliceWithMetadata(wl, podSetName)
	return client.ObjectKeyFromObject(slice)
}

func SliceWithMetadata(wl *kueue.Workload, podSetName kueue.PodSetReference) *v1alpha1.Slice {
	return &v1alpha1.Slice{
		ObjectMeta: metav1.ObjectMeta{
			Name:      SliceName(wl.Name, podSetName),
			Namespace: wl.Namespace,
		},
	}
}

func SliceName(workloadName string, podSetName kueue.PodSetReference) string {
	return fmt.Sprintf("%s-%s", workloadName, podSetName)
}

func Deformed(slice *v1alpha1.Slice) bool {
	return meta.IsStatusConditionTrue(slice.Status.Conditions, string(v1alpha1.Deformed))
}
