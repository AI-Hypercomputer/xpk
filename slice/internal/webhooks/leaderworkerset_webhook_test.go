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
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	leaderworkersetv1 "sigs.k8s.io/lws/api/leaderworkerset/v1"

	slice "tpu-slice-controller/api/v1beta1"
	"tpu-slice-controller/internal/core"
	utiltesting "tpu-slice-controller/internal/util/testing"
	testingjobslws "tpu-slice-controller/internal/util/testingjobs/leaderworkerset"
	"tpu-slice-controller/test/utils"
)

func TestLeaderWorkerSetDefault(t *testing.T) {
	const (
		baseName = "lws"
	)

	testCases := map[string]struct {
		defaultSliceHealthValues []string
		lws                      *leaderworkersetv1.LeaderWorkerSet
		wantLWS                  *leaderworkersetv1.LeaderWorkerSet
		wantErr                  error
	}{
		"no queue label": {
			lws: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Size(4).
				WorkerAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Obj(),
			wantLWS: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Size(4).
				WorkerAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Obj(),
		},
		"no tpu topology annotation": {
			lws: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Queue("queue-name").
				Size(4).
				WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Obj(),
			wantLWS: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Queue("queue-name").
				Size(4).
				WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Obj(),
		},
		"no tpu accelerator node selector label": {
			lws: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Queue("queue-name").
				Size(4).
				WorkerAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				Obj(),
			wantLWS: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Queue("queue-name").
				Size(4).
				WorkerAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				Obj(),
		},
		"should set default values for worker": {
			defaultSliceHealthValues: []string{core.TPUSliceHealthNodeSelectorHealthy},
			lws: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Queue("queue-name").
				Size(4).
				WorkerAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				WorkerLimit(core.TPUResourceName, "4").
				Obj(),
			wantLWS: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Queue("queue-name").
				Size(4).
				WorkerAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				WorkerAnnotation(kueue.PodSetRequiredTopologyAnnotation, "cloud.google.com/gke-tpu-partition-2x2x4-id").
				WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				WorkerNodeAffinity("cloud.google.com/gke-tpu-partition-2x2x4-state", []string{core.TPUSliceHealthNodeSelectorHealthy}).
				WorkerLimit(core.TPUResourceName, "4").
				Obj(),
		},
		"should set default values for worker and leader": {
			defaultSliceHealthValues: []string{core.TPUSliceHealthNodeSelectorHealthy},
			lws: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Queue("queue-name").
				Size(4).
				WorkerAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				WorkerLimit(core.TPUResourceName, "4").
				LeaderAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				LeaderNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				Obj(),
			wantLWS: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Queue("queue-name").
				Size(4).
				WorkerAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				WorkerAnnotation(podsetGroupName, podsetGroupValue).
				WorkerAnnotation(kueue.PodSetRequiredTopologyAnnotation, "cloud.google.com/gke-tpu-partition-2x2x4-id").
				WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				WorkerNodeAffinity("cloud.google.com/gke-tpu-partition-2x2x4-state", []string{core.TPUSliceHealthNodeSelectorHealthy}).
				WorkerLimit(core.TPUResourceName, "4").
				LeaderAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				LeaderAnnotation(podsetGroupName, podsetGroupValue).
				LeaderAnnotation(kueue.PodSetRequiredTopologyAnnotation, "cloud.google.com/gke-tpu-partition-2x2x4-id").
				LeaderNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				LeaderNodeAffinity("cloud.google.com/gke-tpu-partition-2x2x4-state", []string{core.TPUSliceHealthNodeSelectorHealthy}).
				Obj(),
		},
		"should respect existing NodeSelector for health": {
			defaultSliceHealthValues: []string{core.TPUSliceHealthNodeSelectorHealthy},
			lws: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Queue("queue-name").
				Size(4).
				WorkerAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				WorkerNodeSelector("cloud.google.com/gke-tpu-partition-2x2x4-state", "HEALTHY").
				WorkerLimit(core.TPUResourceName, "4").
				Obj(),
			wantLWS: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Queue("queue-name").
				Size(4).
				WorkerAnnotation(core.TPUSliceTopologyAnnotation, "2x2x4").
				WorkerAnnotation(kueue.PodSetRequiredTopologyAnnotation, "cloud.google.com/gke-tpu-partition-2x2x4-id").
				WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				WorkerNodeSelector("cloud.google.com/gke-tpu-partition-2x2x4-state", "HEALTHY").
				WorkerLimit(core.TPUResourceName, "4").
				Obj(),
		},
		"should return error if topology parsing fails": {
			defaultSliceHealthValues: []string{core.TPUSliceHealthNodeSelectorHealthy},
			lws: testingjobslws.MakeLeaderWorkerSet(baseName, utils.DefaultNamespace).
				Queue("queue-name").
				Size(16).
				WorkerAnnotation(core.TPUSliceTopologyAnnotation, "0x4x4").
				WorkerNodeSelector("cloud.google.com/gke-tpu-accelerator", string(slice.TypeTpu7x)).
				WorkerLimit(core.TPUResourceName, "1").
				Obj(),
			wantErr: errors.New("topology dimensions cannot be zero: 0x4x4"),
		},
	}

	for name, tc := range testCases {
		t.Run(name, func(t *testing.T) {
			ctx := t.Context()
			webhook := &LeaderWorkerSetWebhook{
				DefaultSliceHealthValues: tc.defaultSliceHealthValues,
			}

			gotErr := webhook.Default(ctx, tc.lws)
			if diff := cmp.Diff(tc.wantErr, gotErr, utiltesting.EquateErrors); diff != "" {
				t.Errorf("Default() error mismatch (-want +got):\n%s", diff)
			}
			if tc.wantLWS != nil {
				if diff := cmp.Diff(tc.wantLWS, tc.lws); diff != "" {
					t.Errorf("Default() mismatch (-want,+got):\n%s", diff)
				}
			}
		})
	}
}
