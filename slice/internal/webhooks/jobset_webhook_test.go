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
	"github.com/google/go-cmp/cmp/cmpopts"
	"k8s.io/utils/ptr"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueuealpha "sigs.k8s.io/kueue/apis/kueue/v1alpha1"

	testingjobjobset "tpu-slice-controller/internal/util/testingjobs/jobset"
	"tpu-slice-controller/test/utils"
)

func TestDefault(t *testing.T) {
	const (
		baseJobSetName = "jobset"
	)

	testCases := map[string]struct {
		jobSet     *jobset.JobSet
		wantJobSet *jobset.JobSet
		wantErr    error
	}{
		"no queue label": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						TPUTopologyAnnotation: "4x4x12",
						TPUBlockAnnotation:    "cloud.google.com/topology-rack",
						TPUSubBlockAnnotation: "cloud.google.com/topology-host",
					},
					NodeSelector: map[string]string{
						TPUAcceleratorLabel: "tpu-v7x",
					},
				}).
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						TPUTopologyAnnotation: "4x4x12",
						TPUBlockAnnotation:    "cloud.google.com/topology-rack",
						TPUSubBlockAnnotation: "cloud.google.com/topology-host",
					},
					NodeSelector: map[string]string{
						TPUAcceleratorLabel: "tpu-v7x",
					},
				}).
				Obj(),
		},
		"no tpu topology annotation": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						TPUBlockAnnotation:    "cloud.google.com/topology-rack",
						TPUSubBlockAnnotation: "cloud.google.com/topology-host",
					},
					NodeSelector: map[string]string{
						TPUAcceleratorLabel: "tpu-v7x",
					},
				}).
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						TPUBlockAnnotation:    "cloud.google.com/topology-rack",
						TPUSubBlockAnnotation: "cloud.google.com/topology-host",
					},
					NodeSelector: map[string]string{
						TPUAcceleratorLabel: "tpu-v7x",
					},
				}).
				Obj(),
		},
		"no tpu accelerator node selector label": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						TPUTopologyAnnotation: "4x4x12",
						TPUBlockAnnotation:    "cloud.google.com/topology-rack",
						TPUSubBlockAnnotation: "cloud.google.com/topology-host",
					},
				}).
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						TPUTopologyAnnotation: "4x4x12",
						TPUBlockAnnotation:    "cloud.google.com/topology-rack",
						TPUSubBlockAnnotation: "cloud.google.com/topology-host",
					},
				}).
				Obj(),
		},
		"should set default values": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						TPUTopologyAnnotation: "4x4x12",
						TPUBlockAnnotation:    "cloud.google.com/topology-rack",
						TPUSubBlockAnnotation: "cloud.google.com/topology-host",
					},
					NodeSelector: map[string]string{
						TPUAcceleratorLabel: "tpu-v7x",
					},
				}).
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					Annotations: map[string]string{
						kueuealpha.PodSetRequiredTopologyAnnotation:      "cloud.google.com/topology-rack",
						kueuealpha.PodSetSliceRequiredTopologyAnnotation: "cloud.google.com/topology-host",
						kueuealpha.PodSetSliceSizeAnnotation:             "4",
					},
					PodAnnotations: map[string]string{
						TPUTopologyAnnotation: "4x4x12",
						TPUBlockAnnotation:    "cloud.google.com/topology-rack",
						TPUSubBlockAnnotation: "cloud.google.com/topology-host",
					},
					NodeSelector: map[string]string{
						TPUAcceleratorLabel: "tpu-v7x",
					},
				}).
				Obj(),
		},
		"shouldn't set default values because invalid topology annotation": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						TPUTopologyAnnotation: "invalid",
						TPUBlockAnnotation:    "cloud.google.com/topology-rack",
						TPUSubBlockAnnotation: "cloud.google.com/topology-host",
					},
					NodeSelector: map[string]string{
						TPUAcceleratorLabel: "tpu-v7x",
					},
				}).
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						TPUTopologyAnnotation: "invalid",
						TPUBlockAnnotation:    "cloud.google.com/topology-rack",
						TPUSubBlockAnnotation: "cloud.google.com/topology-host",
					},
					NodeSelector: map[string]string{
						TPUAcceleratorLabel: "tpu-v7x",
					},
				}).
				Obj(),
			wantErr: errInvalidTPUTopologyAnnotation,
		},
	}

	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			ctx := t.Context()
			webhook := &JobSetWebhook{}

			gotErr := webhook.Default(ctx, tc.jobSet)
			if diff := cmp.Diff(tc.wantErr, gotErr, cmpopts.EquateErrors()); diff != "" {
				t.Errorf("Default() error mismatch (-want +got):\n%s", diff)
			}
			if tc.wantJobSet != nil {
				if diff := cmp.Diff(tc.wantJobSet, tc.jobSet); diff != "" {
					t.Errorf("Default() mismatch (-want,+got):\n%s", diff)
				}
			}
		})
	}
}

func TestPodSetSliceSize(t *testing.T) {
	testCases := map[string]struct {
		tpuTopology         string
		parallelism         *int32
		wantPodSetSliceSize int32
		wantErr             error
	}{
		"invalid dimension count (1D)": {
			tpuTopology: "2",
			parallelism: ptr.To[int32](12),
			wantErr:     errInvalidTPUTopologyAnnotation,
		},
		"invalid dimension count (4D)": {
			tpuTopology: "2x2x2x2",
			parallelism: ptr.To[int32](12),
			wantErr:     errInvalidTPUTopologyAnnotation,
		},
		"empty dimension": {
			tpuTopology: "xx",
			parallelism: ptr.To[int32](12),
			wantErr:     errInvalidTPUTopologyAnnotation,
		},
		"failed to parse dimension": {
			tpuTopology: "invalidxinvalidxinvalid",
			parallelism: ptr.To[int32](12),
			wantErr:     errInvalidTPUTopologyAnnotation,
		},
		"valid topology annotation": {
			tpuTopology:         "4x4x12",
			parallelism:         ptr.To[int32](12),
			wantPodSetSliceSize: 4,
		},
	}
	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			size, err := podSetSliceSize(tc.tpuTopology, tc.parallelism)
			if diff := cmp.Diff(tc.wantPodSetSliceSize, size); diff != "" {
				t.Errorf("Size mismatch (-want,+got):\n%s", diff)
			}
			if diff := cmp.Diff(tc.wantErr, err, cmpopts.EquateErrors()); diff != "" {
				t.Errorf("Error mismatch (-want +got):\n%s", diff)
			}
		})
	}
}
