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
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	"sigs.k8s.io/controller-runtime/pkg/client"

	utilclient "tpu-slice-controller/internal/util/client"
	"tpu-slice-controller/test/utils"
)

const (
	extraResource  = "cloud.google.com/tpu"
	nodeGroupLabel = "cloud.google.com/gke-node-group"
	nodeGroup      = "tas-group"
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

	nodes := &corev1.NodeList{}
	requiredLabels := client.MatchingLabels{}
	requiredLabelKeys := client.HasLabels{nodeGroupLabel}
	err := k8sClient.List(ctx, nodes, requiredLabels, requiredLabelKeys)
	gomega.Expect(err).NotTo(gomega.HaveOccurred(), "failed to list nodes for TAS")

	for _, n := range nodes.Items {
		gomega.Eventually(func(g gomega.Gomega) {
			node := &corev1.Node{}
			g.Expect(k8sClient.Get(ctx, client.ObjectKey{Name: n.Name}, node)).To(gomega.Succeed())
			err := utilclient.PatchStatus(ctx, k8sClient, node, func() (bool, error) {
				node.Status.Capacity[extraResource] = resource.MustParse("64")
				node.Status.Allocatable[extraResource] = resource.MustParse("64")
				return true, nil
			})
			g.Expect(err).NotTo(gomega.HaveOccurred())
		}, utils.Timeout, utils.Interval).Should(gomega.Succeed())
	}
})
