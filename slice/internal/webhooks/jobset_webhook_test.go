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
	"errors"
	"testing"

	"github.com/google/go-cmp/cmp"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/core"
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
						core.TPUSliceTopologyAnnotation: "4x4x12",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
					},
				}).
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "4x4x12",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
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
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
					},
				}).
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
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
						core.TPUSliceTopologyAnnotation: "4x4x12",
					},
				}).
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "4x4x12",
					},
				}).
				Obj(),
		},
		"should set default values": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 48,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "4x4x12",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
					},
				}).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 48,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation:                 "4x4x12",
						"kueue.x-k8s.io/podset-required-topology":       "cloud.google.com/gce-topology-block",
						"kueue.x-k8s.io/podset-slice-required-topology": core.TPUSubBlockLabel,
						"kueue.x-k8s.io/podset-slice-size":              "16",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
					},
				}).NodeAffinity("rj1", core.TPUSliceHealthNodeSelectorKey, []string{core.TPUSliceHealthNodeSelectorHealthy}).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj(),
		},
		"shouldn't set default values because invalid topology annotation": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "invalid",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
					},
				}).
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "invalid",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
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
						core.TPUSliceTopologyAnnotation: "4x4x12",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": "test",
					},
				}).
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 12,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "4x4x12",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": "test",
					},
				}).
				Obj(),
		},
		"should respect existing NodeSelector for health": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 48,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "4x4x12",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
						core.TPUSliceHealthNodeSelectorKey:     "HEALTHY",
					},
				}).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 48,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation:                 "4x4x12",
						"kueue.x-k8s.io/podset-required-topology":       "cloud.google.com/gce-topology-block",
						"kueue.x-k8s.io/podset-slice-required-topology": core.TPUSubBlockLabel,
						"kueue.x-k8s.io/podset-slice-size":              "16",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
						core.TPUSliceHealthNodeSelectorKey:     "HEALTHY",
					},
				}).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj(),
		},
		"should respect existing NodeAffinity for health": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 48,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "4x4x12",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
					},
				}).
				NodeAffinity("rj1", core.TPUSliceHealthNodeSelectorKey, []string{"HEALTHY"}).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj(),
			wantJobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 48,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation:                 "4x4x12",
						"kueue.x-k8s.io/podset-required-topology":       "cloud.google.com/gce-topology-block",
						"kueue.x-k8s.io/podset-slice-required-topology": core.TPUSubBlockLabel,
						"kueue.x-k8s.io/podset-slice-size":              "16",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
					},
				}).
				NodeAffinity("rj1", core.TPUSliceHealthNodeSelectorKey, []string{"HEALTHY"}).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj(),
		},
		"should reject incorrectly configured replicated job not utilizing entire cube; single cube": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 16,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "4x4x4",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
					},
				}).
				RequestAndLimit("rj1", core.TPUResourceName, "1").
				Obj(),
			wantErr: errors.New("invalid replicated job \"rj1\": configuration results in 16 TPUs requested per cube, but must be exactly 64 TPUs (full utilization)"),
		},
		"should reject incorrectly configured replicated job not utilizing entire cube; multiple cubes": {
			jobSet: testingjobjobset.MakeJobSet(baseJobSetName, utils.DefaultNamespace).
				Queue("queue-name").
				ReplicatedJobs(testingjobjobset.ReplicatedJobRequirements{
					Name:        "rj1",
					Parallelism: 16,
					PodAnnotations: map[string]string{
						core.TPUSliceTopologyAnnotation: "4x4x8",
					},
					NodeSelector: map[string]string{
						"cloud.google.com/gke-tpu-accelerator": string(slice.TypeTpu7x),
					},
				}).
				RequestAndLimit("rj1", core.TPUResourceName, "4").
				Obj(),
			wantErr: errors.New("invalid replicated job \"rj1\": configuration results in 32 TPUs requested per cube, but must be exactly 64 TPUs (full utilization)"),
		},
	}

	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			ctx := t.Context()
			webhook := &JobSetWebhook{}

			gotErr := webhook.Default(ctx, tc.jobSet)
			if diff := cmp.Diff(tc.wantErr, gotErr, cmp.Comparer(func(x, y error) bool {
				if x == nil || y == nil {
					return x == nil && y == nil
				}
				return x.Error() == y.Error()
			})); diff != "" {
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

func TestParseTopology(t *testing.T) {
	testCases := map[string]struct {
		topology string
		wantDims []int64
		wantErr  bool
	}{
		"valid 4x4x4": {
			topology: "4x4x4",
			wantDims: []int64{4, 4, 4},
			wantErr:  false,
		},
		"valid 4x4x8": {
			topology: "4x4x8",
			wantDims: []int64{4, 4, 8},
			wantErr:  false,
		},
		"valid max 16x24x24": {
			topology: "16x24x24",
			wantDims: []int64{16, 24, 24},
			wantErr:  false,
		},
		"invalid format (2 dims)": {
			topology: "4x4",
			wantErr:  true,
		},
		"invalid format (4 dims)": {
			topology: "4x4x4x4",
			wantErr:  true,
		},
		"invalid format (non-int)": {
			topology: "4x4xa",
			wantErr:  true,
		},
		"not divisible by 4": {
			topology: "3x4x4",
			wantErr:  true,
		},
		"not non-decreasing": {
			topology: "8x4x4",
			wantErr:  true,
		},
		"exceeds max": {
			topology: "20x24x24",
			wantErr:  true,
		},
		"zero dimension": {
			topology: "0x4x4",
			wantErr:  true,
		},
		"unparseable": {
			topology: "4x4x4x",
			wantErr:  true,
		},
		"incomplete": {
			topology: "4x4x",
			wantErr:  true,
		},
	}

	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			dims, err := parseTopology(tc.topology)
			if (err != nil) != tc.wantErr {
				t.Errorf("parseTopology() error = %v, wantErr %v", err, tc.wantErr)
				return
			}
			if !tc.wantErr {
				if diff := cmp.Diff(tc.wantDims, dims); diff != "" {
					t.Errorf("parseTopology() mismatch (-want +got):\n%s", diff)
				}
			}
		})
	}
}
