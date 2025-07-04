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

package e2e

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/onsi/ginkgo/v2"
	"github.com/onsi/gomega"
	"sigs.k8s.io/controller-runtime/pkg/client"

	"tpu-slice-controller/test/utils"
)

var (
	k8sClient client.WithWatch
	ctx       context.Context
)

func TestAPIs(t *testing.T) {
	suiteName := "End To End Suite"
	if ver, found := os.LookupEnv("E2E_KIND_VERSION"); found {
		suiteName = fmt.Sprintf("%s: %s", suiteName, ver)
	}
	gomega.RegisterFailHandler(ginkgo.Fail)
	ginkgo.RunSpecs(t,
		suiteName,
	)
}

var _ = ginkgo.BeforeSuite(func() {
	utils.SetupLogger()

	k8sClient, _ = utils.CreateClientUsingCluster("")
	ctx = ginkgo.GinkgoT().Context()

	waitForAvailableStart := time.Now()

	utils.WaitForSliceAvailability(ctx, k8sClient)
	utils.WaitForKueueAvailability(ctx, k8sClient)
	utils.WaitForJobSetAvailability(ctx, k8sClient)
	ginkgo.GinkgoLogr.Info(
		"Slice and all required operators are available in the cluster",
		"waitingTime", time.Since(waitForAvailableStart),
	)
})
