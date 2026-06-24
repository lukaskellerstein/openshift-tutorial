package controller

import (
	"context"
	"fmt"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/intstr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	routev1 "github.com/openshift/api/route/v1"

	tutorialv1alpha1 "github.com/example/webapp-operator/api/v1alpha1"
)

// WebAppReconciler reconciles a WebApp object
type WebAppReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=tutorial.openshift.io,resources=webapps,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=tutorial.openshift.io,resources=webapps/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=tutorial.openshift.io,resources=webapps/finalizers,verbs=update
// +kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=services,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=route.openshift.io,resources=routes,verbs=get;list;watch;create;update;patch;delete

// Reconcile handles create/update/delete events for WebApp custom resources.
// It ensures that a Deployment, Service, and (optionally) Route exist and
// match the desired state described in the WebApp spec.
func (r *WebAppReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// ---------------------------------------------------------------
	// 1. Fetch the WebApp CR
	// ---------------------------------------------------------------
	webapp := &tutorialv1alpha1.WebApp{}
	if err := r.Get(ctx, req.NamespacedName, webapp); err != nil {
		if apierrors.IsNotFound(err) {
			// CR was deleted — child resources will be garbage-collected
			// via owner references. Nothing to do.
			log.Info("WebApp resource not found — probably deleted")
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// ---------------------------------------------------------------
	// 2. Reconcile the Deployment
	// ---------------------------------------------------------------
	deployment := &appsv1.Deployment{}
	deploymentName := types.NamespacedName{Name: webapp.Name, Namespace: webapp.Namespace}
	err := r.Get(ctx, deploymentName, deployment)

	if err != nil && apierrors.IsNotFound(err) {
		// Deployment does not exist — create it
		dep := r.deploymentForWebApp(webapp)
		if err := controllerutil.SetControllerReference(webapp, dep, r.Scheme); err != nil {
			return ctrl.Result{}, fmt.Errorf("failed to set controller reference on Deployment: %w", err)
		}
		log.Info("Creating Deployment", "name", dep.Name, "namespace", dep.Namespace)
		if err := r.Create(ctx, dep); err != nil {
			return ctrl.Result{}, fmt.Errorf("failed to create Deployment: %w", err)
		}
		// Re-fetch after creation so we have the latest version
		if err := r.Get(ctx, deploymentName, deployment); err != nil {
			return ctrl.Result{}, err
		}
	} else if err != nil {
		return ctrl.Result{}, err
	} else {
		// Deployment exists — check if it needs updating
		needsUpdate := false
		if *deployment.Spec.Replicas != webapp.Spec.Replicas {
			deployment.Spec.Replicas = &webapp.Spec.Replicas
			needsUpdate = true
		}
		if deployment.Spec.Template.Spec.Containers[0].Image != webapp.Spec.Image {
			deployment.Spec.Template.Spec.Containers[0].Image = webapp.Spec.Image
			needsUpdate = true
		}
		if needsUpdate {
			log.Info("Updating Deployment", "name", deployment.Name)
			if err := r.Update(ctx, deployment); err != nil {
				return ctrl.Result{}, fmt.Errorf("failed to update Deployment: %w", err)
			}
		}
	}

	// ---------------------------------------------------------------
	// 3. Reconcile the Service
	// ---------------------------------------------------------------
	service := &corev1.Service{}
	serviceName := types.NamespacedName{Name: webapp.Name, Namespace: webapp.Namespace}
	err = r.Get(ctx, serviceName, service)

	if err != nil && apierrors.IsNotFound(err) {
		svc := r.serviceForWebApp(webapp)
		if err := controllerutil.SetControllerReference(webapp, svc, r.Scheme); err != nil {
			return ctrl.Result{}, fmt.Errorf("failed to set controller reference on Service: %w", err)
		}
		log.Info("Creating Service", "name", svc.Name, "namespace", svc.Namespace)
		if err := r.Create(ctx, svc); err != nil {
			return ctrl.Result{}, fmt.Errorf("failed to create Service: %w", err)
		}
	} else if err != nil {
		return ctrl.Result{}, err
	}

	// ---------------------------------------------------------------
	// 4. Reconcile the Route (conditionally)
	// ---------------------------------------------------------------
	route := &routev1.Route{}
	routeName := types.NamespacedName{Name: webapp.Name, Namespace: webapp.Namespace}
	routeExists := false
	err = r.Get(ctx, routeName, route)

	if err == nil {
		routeExists = true
	} else if !apierrors.IsNotFound(err) {
		return ctrl.Result{}, err
	}

	if webapp.Spec.RouteEnabled && !routeExists {
		// Route should exist but does not — create it
		rt := r.routeForWebApp(webapp)
		if err := controllerutil.SetControllerReference(webapp, rt, r.Scheme); err != nil {
			return ctrl.Result{}, fmt.Errorf("failed to set controller reference on Route: %w", err)
		}
		log.Info("Creating Route", "name", rt.Name, "namespace", rt.Namespace)
		if err := r.Create(ctx, rt); err != nil {
			return ctrl.Result{}, fmt.Errorf("failed to create Route: %w", err)
		}
		// Re-fetch to get the assigned host
		if err := r.Get(ctx, routeName, route); err != nil {
			return ctrl.Result{}, err
		}
		routeExists = true
	} else if !webapp.Spec.RouteEnabled && routeExists {
		// Route exists but should not — delete it
		log.Info("Deleting Route (routeEnabled=false)", "name", route.Name)
		if err := r.Delete(ctx, route); err != nil {
			return ctrl.Result{}, fmt.Errorf("failed to delete Route: %w", err)
		}
		routeExists = false
	}

	// ---------------------------------------------------------------
	// 5. Update status
	// ---------------------------------------------------------------
	webapp.Status.AvailableReplicas = deployment.Status.AvailableReplicas

	if routeExists && route.Spec.Host != "" {
		webapp.Status.RouteURL = fmt.Sprintf("https://%s", route.Spec.Host)
	} else {
		webapp.Status.RouteURL = ""
	}

	// Set the Available condition
	condition := metav1.Condition{
		Type:               "Available",
		LastTransitionTime: metav1.Now(),
	}
	if deployment.Status.AvailableReplicas == webapp.Spec.Replicas {
		condition.Status = metav1.ConditionTrue
		condition.Reason = "AllReplicasAvailable"
		condition.Message = fmt.Sprintf("%d/%d replicas are available",
			deployment.Status.AvailableReplicas, webapp.Spec.Replicas)
	} else {
		condition.Status = metav1.ConditionFalse
		condition.Reason = "ReplicasUnavailable"
		condition.Message = fmt.Sprintf("%d/%d replicas are available",
			deployment.Status.AvailableReplicas, webapp.Spec.Replicas)
	}
	setCondition(&webapp.Status.Conditions, condition)

	if err := r.Status().Update(ctx, webapp); err != nil {
		return ctrl.Result{}, fmt.Errorf("failed to update WebApp status: %w", err)
	}

	log.Info("Reconciliation complete",
		"name", webapp.Name,
		"availableReplicas", webapp.Status.AvailableReplicas,
		"routeURL", webapp.Status.RouteURL,
	)

	return ctrl.Result{}, nil
}

// ---------------------------------------------------------------
// Helper: build a Deployment for the WebApp
// ---------------------------------------------------------------
func (r *WebAppReconciler) deploymentForWebApp(w *tutorialv1alpha1.WebApp) *appsv1.Deployment {
	labels := map[string]string{
		"app":              w.Name,
		"tutorial-level":   "2",
		"tutorial-module":  "M2",
		"app.kubernetes.io/managed-by": "webapp-operator",
	}

	container := corev1.Container{
		Name:  "webapp",
		Image: w.Spec.Image,
		Ports: []corev1.ContainerPort{
			{
				ContainerPort: w.Spec.Port,
				Protocol:      corev1.ProtocolTCP,
			},
		},
	}

	// Set resource requests/limits if specified
	if w.Spec.Resources != nil {
		container.Resources = corev1.ResourceRequirements{}
		if w.Spec.Resources.CPURequest != "" || w.Spec.Resources.MemoryRequest != "" {
			container.Resources.Requests = corev1.ResourceList{}
			if w.Spec.Resources.CPURequest != "" {
				container.Resources.Requests[corev1.ResourceCPU] = resource.MustParse(w.Spec.Resources.CPURequest)
			}
			if w.Spec.Resources.MemoryRequest != "" {
				container.Resources.Requests[corev1.ResourceMemory] = resource.MustParse(w.Spec.Resources.MemoryRequest)
			}
		}
		if w.Spec.Resources.CPULimit != "" || w.Spec.Resources.MemoryLimit != "" {
			container.Resources.Limits = corev1.ResourceList{}
			if w.Spec.Resources.CPULimit != "" {
				container.Resources.Limits[corev1.ResourceCPU] = resource.MustParse(w.Spec.Resources.CPULimit)
			}
			if w.Spec.Resources.MemoryLimit != "" {
				container.Resources.Limits[corev1.ResourceMemory] = resource.MustParse(w.Spec.Resources.MemoryLimit)
			}
		}
	}

	dep := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      w.Name,
			Namespace: w.Namespace,
			Labels:    labels,
		},
		Spec: appsv1.DeploymentSpec{
			Replicas: &w.Spec.Replicas,
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{"app": w.Name},
			},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: labels,
				},
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{container},
				},
			},
		},
	}

	return dep
}

// ---------------------------------------------------------------
// Helper: build a Service for the WebApp
// ---------------------------------------------------------------
func (r *WebAppReconciler) serviceForWebApp(w *tutorialv1alpha1.WebApp) *corev1.Service {
	return &corev1.Service{
		ObjectMeta: metav1.ObjectMeta{
			Name:      w.Name,
			Namespace: w.Namespace,
			Labels: map[string]string{
				"app":             w.Name,
				"tutorial-level":  "2",
				"tutorial-module": "M2",
			},
		},
		Spec: corev1.ServiceSpec{
			Selector: map[string]string{"app": w.Name},
			Ports: []corev1.ServicePort{
				{
					Port:       w.Spec.Port,
					TargetPort: intstr.FromInt32(w.Spec.Port),
					Protocol:   corev1.ProtocolTCP,
				},
			},
		},
	}
}

// ---------------------------------------------------------------
// Helper: build a Route for the WebApp
// ---------------------------------------------------------------
func (r *WebAppReconciler) routeForWebApp(w *tutorialv1alpha1.WebApp) *routev1.Route {
	return &routev1.Route{
		ObjectMeta: metav1.ObjectMeta{
			Name:      w.Name,
			Namespace: w.Namespace,
			Labels: map[string]string{
				"app":             w.Name,
				"tutorial-level":  "2",
				"tutorial-module": "M2",
			},
		},
		Spec: routev1.RouteSpec{
			To: routev1.RouteTargetReference{
				Kind: "Service",
				Name: w.Name,
			},
			Port: &routev1.RoutePort{
				TargetPort: intstr.FromInt32(w.Spec.Port),
			},
			TLS: &routev1.TLSConfig{
				Termination: routev1.TLSTerminationEdge,
			},
		},
	}
}

// ---------------------------------------------------------------
// Helper: set or update a condition in the conditions slice
// ---------------------------------------------------------------
func setCondition(conditions *[]metav1.Condition, newCondition metav1.Condition) {
	for i, c := range *conditions {
		if c.Type == newCondition.Type {
			(*conditions)[i] = newCondition
			return
		}
	}
	*conditions = append(*conditions, newCondition)
}

// SetupWithManager sets up the controller with the Manager.
// It watches WebApp CRs and also watches owned Deployments, Services, and
// Routes so that changes to those child resources trigger reconciliation.
func (r *WebAppReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&tutorialv1alpha1.WebApp{}).
		Owns(&appsv1.Deployment{}).
		Owns(&corev1.Service{}).
		Owns(&routev1.Route{}).
		Complete(r)
}
