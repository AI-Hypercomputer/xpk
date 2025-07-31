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

package utils

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/go-logr/logr"
	"github.com/onsi/ginkgo/v2"
	"github.com/onsi/gomega"
	zaplog "go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/utils/ptr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
	jobset "sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueue "sigs.k8s.io/kueue/apis/kueue/v1beta1"
	podconstants "sigs.k8s.io/kueue/pkg/controller/jobs/pod/constants"

	"tpu-slice-controller/internal/controller"
	"tpu-slice-controller/internal/util/testing"
)

const (
	defaultLogLevel = -3
)

func logLevel() int {
	level, err := strconv.Atoi(os.Getenv("TEST_LOG_LEVEL"))
	if err != nil {
		return defaultLogLevel
	}
	return level
}

var SetupLogger = sync.OnceFunc(func() {
	ctrl.SetLogger(NewTestingLogger(ginkgo.GinkgoWriter, logLevel()))
})

func NewTestingLogger(writer io.Writer, level int) logr.Logger {
	opts := func(o *zap.Options) {
		o.TimeEncoder = zapcore.RFC3339NanoTimeEncoder
		o.ZapOpts = []zaplog.Option{zaplog.AddCaller()}
	}
	return zap.New(
		zap.WriteTo(writer),
		zap.UseDevMode(true),
		zap.Level(zapcore.Level(level)),
		opts)
}

func GetSliceNamespace() string {
	if ns := os.Getenv("SLICE_NAMESPACE"); ns != "" {
		return ns
	}
	return DefaultNamespace
}

// Run executes the provided command within this context
func Run(cmd *exec.Cmd) (string, error) {
	dir, _ := GetProjectDir()
	cmd.Dir = dir

	if err := os.Chdir(cmd.Dir); err != nil {
		_, _ = fmt.Fprintf(ginkgo.GinkgoWriter, "chdir dir: %q\n", err)
	}

	cmd.Env = append(os.Environ(), "GO111MODULE=on")
	command := strings.Join(cmd.Args, " ")
	_, _ = fmt.Fprintf(ginkgo.GinkgoWriter, "running: %q\n", command)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return string(output), fmt.Errorf("%q failed with error %q: %w", command, string(output), err)
	}

	return string(output), nil
}

// GetNonEmptyLines converts given command output string into individual objects
// according to line breakers, and ignores the empty elements in it.
func GetNonEmptyLines(output string) []string {
	var res []string
	elements := strings.Split(output, "\n")
	for _, element := range elements {
		if element != "" {
			res = append(res, element)
		}
	}

	return res
}

// GetProjectDir will return the directory where the project is
func GetProjectDir() (string, error) {
	wd, err := os.Getwd()
	if err != nil {
		return wd, fmt.Errorf("failed to get current working directory: %w", err)
	}
	wd = strings.ReplaceAll(wd, "/test/e2e", "")
	return wd, nil
}

func ExpectAllPodsInNamespaceDeleted(ctx context.Context, c client.Client, ns *corev1.Namespace) {
	ginkgo.GinkgoHelper()
	pods := corev1.PodList{}
	gomega.Eventually(func(g gomega.Gomega) {
		g.Expect(c.List(ctx, &pods, client.InNamespace(ns.Name))).Should(gomega.Succeed())
		g.Expect(pods.Items).Should(gomega.BeEmpty())
	}, LongTimeout, Interval).Should(gomega.Succeed())
}

func deleteAllObjectsInNamespace(ctx context.Context, c client.Client, ns *corev1.Namespace, obj client.Object) error {
	err := c.DeleteAllOf(ctx, obj, client.InNamespace(ns.Name), client.PropagationPolicy(metav1.DeletePropagationBackground))
	if err != nil && !apierrors.IsNotFound(err) && !errors.Is(err, &meta.NoKindMatchError{}) {
		return err
	}
	return nil
}

func DeleteAllJobSetsInNamespace(ctx context.Context, c client.Client, ns *corev1.Namespace) error {
	return deleteAllObjectsInNamespace(ctx, c, ns, &jobset.JobSet{})
}

func DeleteAllJobsInNamespace(ctx context.Context, c client.Client, ns *corev1.Namespace) error {
	return deleteAllObjectsInNamespace(ctx, c, ns, &batchv1.Job{})
}

func DeleteAllPodsInNamespace(ctx context.Context, c client.Client, ns *corev1.Namespace) {
	gomega.ExpectWithOffset(1, deleteAllPodsInNamespace(ctx, c, ns, 2)).To(gomega.Succeed())
}

func deleteAllPodsInNamespace(ctx context.Context, c client.Client, ns *corev1.Namespace, offset int) error {
	if err := client.IgnoreNotFound(c.DeleteAllOf(ctx, &corev1.Pod{}, client.InNamespace(ns.Name))); err != nil {
		return fmt.Errorf("deleting all Pods in namespace %q: %w", ns.Name, err)
	}
	gomega.EventuallyWithOffset(offset, func(g gomega.Gomega) {
		pods := corev1.PodList{}
		g.Expect(client.IgnoreNotFound(c.List(ctx, &pods, client.InNamespace(ns.Name)))).
			Should(gomega.Succeed(), "listing Pods with a finalizer in namespace %q", ns.Name)
		for _, p := range pods.Items {
			if controllerutil.RemoveFinalizer(&p, podconstants.PodFinalizer) {
				g.Expect(client.IgnoreNotFound(c.Update(ctx, &p))).Should(gomega.Succeed(), "removing finalizer")
			}
			opts := &client.DeleteOptions{
				GracePeriodSeconds: ptr.To[int64](0),
			}
			err := c.Delete(ctx, &p, opts)
			g.Expect(client.IgnoreNotFound(err)).To(gomega.Succeed())
		}
	}, LongTimeout, Interval).Should(gomega.Succeed())
	return nil
}

func deleteWorkloadsInNamespace(ctx context.Context, c client.Client, ns *corev1.Namespace, offset int) error {
	if err := c.DeleteAllOf(ctx, &kueue.Workload{}, client.InNamespace(ns.Name)); err != nil && !apierrors.IsNotFound(err) {
		return err
	}
	gomega.EventuallyWithOffset(offset, func(g gomega.Gomega) {
		workloads := kueue.WorkloadList{}
		g.Expect(c.List(ctx, &workloads, client.InNamespace(ns.Name))).Should(gomega.Succeed())
		for _, wl := range workloads.Items {
			update := false
			if controllerutil.RemoveFinalizer(&wl, kueue.ResourceInUseFinalizerName) {
				update = true
			}
			if controllerutil.RemoveFinalizer(&wl, controller.SliceControllerName) {
				update = true
			}
			if update {
				g.Expect(client.IgnoreNotFound(c.Update(ctx, &wl))).Should(gomega.Succeed())
			}
		}
	}, LongTimeout, Interval).Should(gomega.Succeed())
	return nil
}

type objAsPtr[T any] interface {
	client.Object
	*T
}

func DeleteObject[PtrT objAsPtr[T], T any](ctx context.Context, c client.Client, o PtrT) error {
	if o != nil {
		if err := c.Delete(ctx, o); err != nil && !apierrors.IsNotFound(err) {
			return err
		}
	}
	return nil
}

func expectObjectToBeDeletedWithTimeout[PtrT objAsPtr[T], T any](ctx context.Context, k8sClient client.Client, o PtrT, deleteNow bool, timeout time.Duration) {
	if o == nil {
		return
	}
	if deleteNow {
		gomega.ExpectWithOffset(2, client.IgnoreNotFound(DeleteObject(ctx, k8sClient, o))).To(gomega.Succeed())
	}
	gomega.EventuallyWithOffset(2, func(g gomega.Gomega) {
		newObj := PtrT(new(T))
		g.Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(o), newObj)).Should(testing.BeNotFoundError())
	}, timeout, Interval).Should(gomega.Succeed())
}

func ExpectObjectToBeDeleted[PtrT objAsPtr[T], T any](ctx context.Context, k8sClient client.Client, o PtrT, deleteNow bool) {
	expectObjectToBeDeletedWithTimeout(ctx, k8sClient, o, deleteNow, Timeout)
}

// DeleteNamespace deletes all objects the tests typically create in the namespace.
func DeleteNamespace(ctx context.Context, c client.Client, ns *corev1.Namespace) error {
	if ns == nil {
		return nil
	}

	if err := DeleteAllJobSetsInNamespace(ctx, c, ns); err != nil {
		return err
	}

	if err := DeleteAllJobsInNamespace(ctx, c, ns); err != nil {
		return err
	}

	if err := deleteAllPodsInNamespace(ctx, c, ns, 2); err != nil {
		return err
	}

	if err := deleteWorkloadsInNamespace(ctx, c, ns, 2); err != nil {
		return err
	}

	if err := c.DeleteAllOf(ctx, &kueue.LocalQueue{}, client.InNamespace(ns.Name)); err != nil && !apierrors.IsNotFound(err) {
		return err
	}

	return nil
}

func MustCreate(ctx context.Context, c client.Client, obj client.Object) {
	ginkgo.GinkgoHelper()
	gomega.Expect(c.Create(ctx, obj)).Should(gomega.Succeed())
}
