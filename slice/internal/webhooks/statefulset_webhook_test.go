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
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/core"
	utiltesting "tpu-slice-controller/internal/util/testing"
)

func TestStatefulSetDefault(t *testing.T) {
	const (
		baseName      = "sts"
		baseNamespace = "default"
	)

	testCases := map[string]struct {
		sts     *appsv1.StatefulSet
		wantSts *appsv1.StatefulSet
		wantErr error
	}{
		"not a relevant statefulset (missing annotation and node selector)": {
			sts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{Name: baseName, Namespace: baseNamespace},
				Spec:       appsv1.StatefulSetSpec{},
			},
			wantSts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{Name: baseName, Namespace: baseNamespace},
				Spec:       appsv1.StatefulSetSpec{},
			},
		},
		"not a relevant statefulset (missing node selector)": {
			sts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{
					Name:      baseName,
					Namespace: baseNamespace,
				},
				Spec: appsv1.StatefulSetSpec{
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Annotations: map[string]string{core.TPUSliceTopologyAnnotation: "4x4x12"},
						},
						Spec: corev1.PodSpec{},
					},
				},
			},
			wantSts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{
					Name:      baseName,
					Namespace: baseNamespace,
				},
				Spec: appsv1.StatefulSetSpec{
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Annotations: map[string]string{core.TPUSliceTopologyAnnotation: "4x4x12"},
						},
						Spec: corev1.PodSpec{},
					},
				},
			},
		},
		"relevant statefulset, missing tpu topology node selector": {
			sts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{
					Name:      baseName,
					Namespace: baseNamespace,
				},
				Spec: appsv1.StatefulSetSpec{
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Annotations: map[string]string{core.TPUSliceTopologyAnnotation: "4x4x12"},
						},
						Spec: corev1.PodSpec{
							NodeSelector: map[string]string{
								core.TPUAcceleratorLabel: string(slice.TypeTpu7x),
							},
						},
					},
				},
			},
			wantSts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{
					Name:      baseName,
					Namespace: baseNamespace,
				},
				Spec: appsv1.StatefulSetSpec{
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Annotations: map[string]string{core.TPUSliceTopologyAnnotation: "4x4x12"},
						},
						Spec: corev1.PodSpec{
							NodeSelector: map[string]string{
								core.TPUAcceleratorLabel:   string(slice.TypeTpu7x),
								core.TPUTopologyAnnotation: "4x4x12",
							},
						},
					},
				},
			},
		},
		"relevant statefulset, with tpu topology node selector already present": {
			sts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{
					Name:      baseName,
					Namespace: baseNamespace,
				},
				Spec: appsv1.StatefulSetSpec{
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Annotations: map[string]string{core.TPUSliceTopologyAnnotation: "4x4x12"},
						},
						Spec: corev1.PodSpec{
							NodeSelector: map[string]string{
								core.TPUAcceleratorLabel:   string(slice.TypeTpu7x),
								core.TPUTopologyAnnotation: "4x4x12",
							},
						},
					},
				},
			},
			wantSts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{
					Name:      baseName,
					Namespace: baseNamespace,
				},
				Spec: appsv1.StatefulSetSpec{
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Annotations: map[string]string{core.TPUSliceTopologyAnnotation: "4x4x12"},
						},
						Spec: corev1.PodSpec{
							NodeSelector: map[string]string{
								core.TPUAcceleratorLabel:   string(slice.TypeTpu7x),
								core.TPUTopologyAnnotation: "4x4x12",
							},
						},
					},
				},
			},
		},
		"relevant statefulset, missing tpu topology node selector and has other node selector": {
			sts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{
					Name:      baseName,
					Namespace: baseNamespace,
				},
				Spec: appsv1.StatefulSetSpec{
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Annotations: map[string]string{core.TPUSliceTopologyAnnotation: "4x4x12"},
						},
						Spec: corev1.PodSpec{
							NodeSelector: map[string]string{
								core.TPUAcceleratorLabel: string(slice.TypeTpu7x),
								"kubernetes.io/os":       "linux",
							},
						},
					},
				},
			},
			wantSts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{
					Name:      baseName,
					Namespace: baseNamespace,
				},
				Spec: appsv1.StatefulSetSpec{
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Annotations: map[string]string{core.TPUSliceTopologyAnnotation: "4x4x12"},
						},
						Spec: corev1.PodSpec{
							NodeSelector: map[string]string{
								core.TPUAcceleratorLabel:   string(slice.TypeTpu7x),
								"kubernetes.io/os":         "linux",
								core.TPUTopologyAnnotation: "4x4x12",
							},
						},
					},
				},
			},
		},
		"relevant statefulset, with tpu topology node selector and other node selector": {
			sts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{
					Name:      baseName,
					Namespace: baseNamespace,
				},
				Spec: appsv1.StatefulSetSpec{
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Annotations: map[string]string{core.TPUSliceTopologyAnnotation: "4x4x12"},
						},
						Spec: corev1.PodSpec{
							NodeSelector: map[string]string{
								core.TPUAcceleratorLabel:   string(slice.TypeTpu7x),
								core.TPUTopologyAnnotation: "4x4x12",
								"kubernetes.io/os":         "linux",
							},
						},
					},
				},
			},
			wantSts: &appsv1.StatefulSet{
				ObjectMeta: metav1.ObjectMeta{
					Name:      baseName,
					Namespace: baseNamespace,
				},
				Spec: appsv1.StatefulSetSpec{
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Annotations: map[string]string{core.TPUSliceTopologyAnnotation: "4x4x12"},
						},
						Spec: corev1.PodSpec{
							NodeSelector: map[string]string{
								core.TPUAcceleratorLabel:   string(slice.TypeTpu7x),
								core.TPUTopologyAnnotation: "4x4x12",
								"kubernetes.io/os":         "linux",
							},
						},
					},
				},
			},
		},
	}

	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			ctx := t.Context()
			webhook := &StatefulSetWebhook{}

			gotErr := webhook.Default(ctx, tc.sts)
			if diff := cmp.Diff(tc.wantErr, gotErr, utiltesting.EquateErrors); diff != "" {
				t.Errorf("Default() error mismatch (-want +got):\n%s", diff)
			}
			if tc.wantSts != nil {
				if diff := cmp.Diff(tc.wantSts, tc.sts); diff != "" {
					t.Errorf("Default() mismatch (-want,+got):\n%s", diff)
				}
			}
		})
	}
}
