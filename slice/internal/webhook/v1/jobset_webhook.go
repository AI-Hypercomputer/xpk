package webhooks

import (
	"context"

	apivalidation "k8s.io/apimachinery/pkg/api/validation"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/util/validation/field"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/webhook"
	"sigs.k8s.io/controller-runtime/pkg/webhook/admission"
	"sigs.k8s.io/jobset/api/jobset/v1alpha2"
	kueueconstants "sigs.k8s.io/kueue/pkg/controller/constants"
)

const (
	PodSetRequiredTopologyAnnotation      = "kueue.x-k8s.io/podset-required-topology"
	PodSetSliceRequiredTopologyAnnotation = "kueue.x-k8s.io/podset-slice-required-topology"
	PodSetSliceSizeAnnotation             = "kueue.x-k8s.io/podset-slice-size"
)

// JobSet is the schema for your resource (ensure this matches your resource definition).
type JobSetWebhook struct{}

func SetupWebhookWithManager(mgr ctrl.Manager) error {
	return ctrl.NewWebhookManagedBy(mgr).
		For(&v1alpha2.JobSet{}).
		WithDefaulter(&JobSetWebhook{}).
		WithValidator(&JobSetWebhook{}).
		Complete()
}

// +kubebuilder:webhook:path=/mutate-jobset-x-k8s-io-v1alpha2-jobset,mutating=true,failurePolicy=fail,sideEffects=None,groups=jobset.x-k8s.io,resources=jobsets,verbs=create,versions=v1alpha2,name=mjobset.kb.io,admissionReviewVersions=v1
// +kubebuilder:webhook:path=/validate-jobset-x-k8s-io-v1alpha2-jobset,mutating=false,failurePolicy=fail,sideEffects=None,groups=jobset.x-k8s.io,resources=jobsets,verbs=create;update,versions=v1alpha2,name=vjobset.kb.io,admissionReviewVersions=v1
var _ webhook.CustomDefaulter = &JobSetWebhook{}
var _ webhook.CustomValidator = &JobSetWebhook{}

// Default implements webhook.CustomDefaulter so a webhook will be registered for the type
func (r *JobSetWebhook) Default(ctx context.Context, obj runtime.Object) error {
	jobSet := obj.(*v1alpha2.JobSet)
	log := ctrl.LoggerFrom(ctx).WithName("jobset-webhook")
	log.V(5).Info("Applying defaults")

	// handle webhooks for Kueue related JobSets
	if cq, ok := jobSet.Labels[kueueconstants.QueueLabel]; ok && cq != "" {
		for i, rj := range jobSet.Spec.ReplicatedJobs {
			if rj.Template.Annotations == nil {
				rj.Template.Annotations = make(map[string]string, 3)
			}
			rj.Template.Annotations[PodSetRequiredTopologyAnnotation] = "TBD"
			rj.Template.Annotations[PodSetSliceRequiredTopologyAnnotation] = "TBD"
			rj.Template.Annotations[PodSetSliceSizeAnnotation] = "TBD"

			jobSet.Spec.ReplicatedJobs[i] = rj
		}
	}

	return nil
}

// ValidateCreate implements webhook.CustomValidator so a webhook will be registered for the type.
func (r *JobSetWebhook) ValidateCreate(ctx context.Context, obj runtime.Object) (admission.Warnings, error) {
	return nil, nil
}

var (
	annotationsPath = field.NewPath("spec", "replicatedJobs", "template", "annotations")
)

// ValidateUpdate implements webhook.CustomValidator so a webhook will be registered for the type.
func (r *JobSetWebhook) ValidateUpdate(ctx context.Context, oldObj, newObj runtime.Object) (admission.Warnings, error) {
	oldJobSet := oldObj.(*v1alpha2.JobSet)
	newJobSet := newObj.(*v1alpha2.JobSet)
	log := ctrl.LoggerFrom(ctx).WithName("jobset-webhook")
	log.Info("Validating update")

	annotationsToValidate := []string{
		PodSetRequiredTopologyAnnotation,
		PodSetSliceRequiredTopologyAnnotation,
		PodSetSliceSizeAnnotation,
	}

	var allErrs field.ErrorList
	for i, oldRj := range oldJobSet.Spec.ReplicatedJobs {
		newRj := newJobSet.Spec.ReplicatedJobs[i]
		for _, annotation := range annotationsToValidate {
			allErrs = append(allErrs, apivalidation.ValidateImmutableField(
				GetAnnotationValue(newRj, annotation),
				GetAnnotationValue(oldRj, annotation),
				annotationsPath.Key(annotation),
			)...)
		}
	}

	return nil, allErrs.ToAggregate()
}

func GetAnnotationValue(obj v1alpha2.ReplicatedJob, annotationName string) string {
	if val, exists := obj.Template.Annotations[annotationName]; exists && val != "" {
		return val
	}
	return ""
}

// ValidateDelete implements webhook.CustomValidator so a webhook will be registered for the type.
func (r *JobSetWebhook) ValidateDelete(_ context.Context, _ runtime.Object) (admission.Warnings, error) {
	return nil, nil
}
