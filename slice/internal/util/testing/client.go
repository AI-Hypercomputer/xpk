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

package testing

import (
	"context"
	"fmt"
	"sync"

	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/tools/record"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

type EventRecord struct {
	Key       types.NamespacedName
	EventType string
	Reason    string
	Message   string
	// add annotations if ever needed
}

type EventRecorder struct {
	lock           sync.Mutex
	RecordedEvents []EventRecord
}

var _ record.EventRecorder = (*EventRecorder)(nil)

func (tr *EventRecorder) Event(object runtime.Object, eventType, reason, message string) {
	tr.generateEvent(object, eventType, reason, message)
}

func (tr *EventRecorder) Eventf(object runtime.Object, eventType, reason, messageFmt string, args ...any) {
	tr.AnnotatedEventf(object, nil, eventType, reason, messageFmt, args...)
}

func (tr *EventRecorder) AnnotatedEventf(targetObject runtime.Object, _ map[string]string, eventType, reason, messageFmt string, args ...any) {
	tr.generateEvent(targetObject, eventType, reason, fmt.Sprintf(messageFmt, args...))
}

func (tr *EventRecorder) generateEvent(targetObject runtime.Object, eventType, reason, message string) {
	tr.lock.Lock()
	defer tr.lock.Unlock()
	key := types.NamespacedName{}
	if cObj, isCObj := targetObject.(client.Object); isCObj {
		key = client.ObjectKeyFromObject(cObj)
	}
	tr.RecordedEvents = append(tr.RecordedEvents, EventRecord{
		Key:       key,
		EventType: eventType,
		Reason:    reason,
		Message:   message,
	})
}

type ssaPatchAsStrategicMerge struct {
	client.Patch
}

func (*ssaPatchAsStrategicMerge) Type() types.PatchType {
	return types.StrategicMergePatchType
}

func wrapSSAPatch(patch client.Patch) client.Patch {
	if patch.Type() == types.ApplyPatchType {
		return &ssaPatchAsStrategicMerge{Patch: patch}
	}
	return patch
}

// TreatSSAAsStrategicMerge - can be used as a SubResourcePatch interceptor function to treat SSA patches as StrategicMergePatchType.
// Note: By doing so the values set in the patch will be updated but the call will have no knowledge of FieldManagement when it
// comes to detecting conflicts between managers or removing fields that are missing from the patch.
func TreatSSAAsStrategicMerge(ctx context.Context, clnt client.Client, subResourceName string, obj client.Object, patch client.Patch, opts ...client.SubResourcePatchOption) error {
	return clnt.SubResource(subResourceName).Patch(ctx, obj, wrapSSAPatch(patch), opts...)
}
