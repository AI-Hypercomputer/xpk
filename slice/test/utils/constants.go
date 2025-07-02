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
	"time"
)

const (
	DefaultNamespace             = "slice-controller-system"
	DefaultControllerManagerName = "slice-controller-controller-manager"
)

const (
	Timeout        = 10 * time.Second
	LongTimeout    = 45 * time.Second
	StartUpTimeout = 5 * time.Minute
	Interval       = time.Millisecond * 250
)

var (
	// For full documentation on agnhost subcommands see the following documentation:
	// https://pkg.go.dev/k8s.io/kubernetes/test/images/agnhost#section-readme

	// BehaviorWaitForDeletion starts a simple HTTP(S) with a few endpoints, one of which is the /exit endpoint which exits with `exit 0`
	BehaviorWaitForDeletion = []string{"netexec"}
)
