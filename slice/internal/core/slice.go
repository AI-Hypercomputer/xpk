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
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"

	"tpu-slice-controller/api/v1alpha1"
)

// TODO: we will soon need to key per podset, in #520
func SliceKeyFromWorkload(wl *kueue.Workload) client.ObjectKey {
	slice := SliceWithMetadata(wl)
	return client.ObjectKeyFromObject(slice)
}

// TODO: we will soon need to key per podset, in #520
func SliceWithMetadata(wl *kueue.Workload) *v1alpha1.Slice {
	return &v1alpha1.Slice{
		ObjectMeta: metav1.ObjectMeta{
			Name:      wl.Name,
			Namespace: wl.Namespace,
		},
	}
}
