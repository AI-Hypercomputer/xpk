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

package features

import (
	"k8s.io/apimachinery/pkg/util/runtime"
	"k8s.io/apimachinery/pkg/util/version"
	utilfeature "k8s.io/apiserver/pkg/util/feature"
	"k8s.io/component-base/featuregate"
	featuregatetesting "k8s.io/component-base/featuregate/testing"
)

const (
	// UseRetryMechanismForSliceCreation enables the retry-on-failure mechanism for Slice creation.
	// When enabled, each Slice is annotated and the Slice Controller (in KCP) automatically
	// retries on creation failures (including upon partition ID conflicts).
	// If a Slice fails to form within the timeout, we evict the Workload.
	UseRetryMechanismForSliceCreation featuregate.Feature = "UseRetryMechanismForSliceCreation"

	// ShorterSliceNameLength enables support for shorter Slice names (max 49 characters).
	ShorterSliceNameLength featuregate.Feature = "ShorterSliceNameLength"
)

var defaultVersionedFeatureGates = map[featuregate.Feature]featuregate.VersionedSpecs{
	UseRetryMechanismForSliceCreation: {
		{Version: version.MustParse("0.1"), Default: false, PreRelease: featuregate.Alpha},
	},
	ShorterSliceNameLength: {
		{Version: version.MustParse("0.1"), Default: false, PreRelease: featuregate.Alpha},
	},
}

func init() {
	runtime.Must(utilfeature.DefaultMutableFeatureGate.AddVersioned(defaultVersionedFeatureGates))
}

func SetFeatureGateDuringTest(tb featuregatetesting.TB, f featuregate.Feature, value bool) {
	featuregatetesting.SetFeatureGateDuringTest(tb, utilfeature.DefaultFeatureGate, f, value)
}

// Enabled is helper for `utilfeature.DefaultFeatureGate.Enabled()`
func Enabled(f featuregate.Feature) bool {
	return utilfeature.DefaultFeatureGate.Enabled(f)
}
