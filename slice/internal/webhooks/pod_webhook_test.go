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

package webhooks

import (
	"testing"

	"github.com/google/go-cmp/cmp"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/core"
	utiltesting "tpu-slice-controller/internal/util/testing"
	testingpod "tpu-slice-controller/internal/util/testingjobs/pod"
)

func TestPodDefault(t *testing.T) {
	const (
		basePodName   = "pod"
		baseNamespace = "default"
	)

	scheme := runtime.NewScheme()
	_ = corev1.AddToScheme(scheme)

	makeTPUPod := func(name, ns string) *testingpod.PodWrapper {
		return testingpod.MakePod(name, ns).
			Annotation(core.TPUSliceTopologyAnnotation, "4x4x4").
			NodeSelector(core.TPUAcceleratorLabel, string(slice.TypeTpu7x))
	}

	testCases := map[string]struct {
		pod     *corev1.Pod
		wantPod *corev1.Pod
		wantErr error
	}{
		"anti-affinity removed": {
			pod: makeTPUPod(basePodName, baseNamespace).NodeSelectorRequirement(corev1.NodeSelectorRequirement{
				Key:      core.TPUSliceNodeLabel,
				Operator: corev1.NodeSelectorOpDoesNotExist,
			}).NodeSelectorRequirement(
				corev1.NodeSelectorRequirement{
					Key:      "other-key",
					Operator: corev1.NodeSelectorOpExists,
				},
			).Obj(),
			wantPod: makeTPUPod(basePodName, baseNamespace).NodeSelectorRequirement(
				corev1.NodeSelectorRequirement{
					Key:      "other-key",
					Operator: corev1.NodeSelectorOpExists,
				},
			).Obj(),
		},
		"no anti-affinity": {
			pod: makeTPUPod(basePodName, baseNamespace).NodeSelectorRequirement(
				corev1.NodeSelectorRequirement{
					Key:      "other-key",
					Operator: corev1.NodeSelectorOpExists,
				},
			).Obj(),
			wantPod: makeTPUPod(basePodName, baseNamespace).NodeSelectorRequirement(
				corev1.NodeSelectorRequirement{
					Key:      "other-key",
					Operator: corev1.NodeSelectorOpExists,
				},
			).Obj(),
		},
	}

	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			ctx := t.Context()
			webhook := &PodWebhook{}

			gotErr := webhook.Default(ctx, tc.pod)
			if diff := cmp.Diff(tc.wantErr, gotErr, utiltesting.EquateErrors); diff != "" {
				t.Errorf("Default() error mismatch (-want +got):\n%s", diff)
			}
			if tc.wantPod != nil {
				if diff := cmp.Diff(tc.wantPod, tc.pod); diff != "" {
					t.Errorf("Default() mismatch (-want,+got):\n%s", diff)
				}
			}
		})
	}
}
