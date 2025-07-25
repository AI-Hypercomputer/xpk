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
						TPUTopologyAnnotation:                            "4x4x12",
						kueuealpha.PodSetRequiredTopologyAnnotation:      TPUBlockLabel,
						kueuealpha.PodSetSliceRequiredTopologyAnnotation: TPUSubBlockLabel,
						kueuealpha.PodSetSliceSizeAnnotation:             "4",
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
					},
					NodeSelector: map[string]string{
						TPUAcceleratorLabel: "tpu-v7x",
					},
				}).
				Obj(),
		},
		"shouldn't set default values because unsupported tpu accelerator": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						TPUTopologyAnnotation: "4x4x12",
					},
					NodeSelector: map[string]string{
						TPUAcceleratorLabel: "test",
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
					},
					NodeSelector: map[string]string{
						TPUAcceleratorLabel: "test",
					},
				}).
				Obj(),
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
