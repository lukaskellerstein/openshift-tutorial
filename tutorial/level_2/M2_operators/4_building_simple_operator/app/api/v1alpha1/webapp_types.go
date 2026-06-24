package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// WebAppSpec defines the desired state of WebApp
type WebAppSpec struct {
	// Image is the container image for the web application
	// +kubebuilder:validation:Required
	Image string `json:"image"`

	// Replicas is the number of desired pod replicas
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=10
	// +kubebuilder:default=1
	Replicas int32 `json:"replicas,omitempty"`

	// Port is the container port the application listens on
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=65535
	// +kubebuilder:default=8080
	Port int32 `json:"port,omitempty"`

	// RouteEnabled controls whether an OpenShift Route is created
	// +kubebuilder:default=true
	RouteEnabled bool `json:"routeEnabled,omitempty"`

	// Resources defines CPU and memory requests/limits
	// +optional
	Resources *ResourceRequirements `json:"resources,omitempty"`
}

// ResourceRequirements defines compute resource requirements
type ResourceRequirements struct {
	// CPURequest is the CPU request (e.g., "100m")
	CPURequest string `json:"cpuRequest,omitempty"`
	// CPULimit is the CPU limit (e.g., "500m")
	CPULimit string `json:"cpuLimit,omitempty"`
	// MemoryRequest is the memory request (e.g., "64Mi")
	MemoryRequest string `json:"memoryRequest,omitempty"`
	// MemoryLimit is the memory limit (e.g., "128Mi")
	MemoryLimit string `json:"memoryLimit,omitempty"`
}

// WebAppStatus defines the observed state of WebApp
type WebAppStatus struct {
	// Conditions represent the latest available observations of the WebApp's state
	Conditions []metav1.Condition `json:"conditions,omitempty"`
	// AvailableReplicas is the number of ready replicas
	AvailableReplicas int32 `json:"availableReplicas,omitempty"`
	// RouteURL is the externally accessible URL (if route is enabled)
	RouteURL string `json:"routeURL,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:printcolumn:name="Image",type=string,JSONPath=`.spec.image`
// +kubebuilder:printcolumn:name="Replicas",type=integer,JSONPath=`.spec.replicas`
// +kubebuilder:printcolumn:name="Available",type=integer,JSONPath=`.status.availableReplicas`
// +kubebuilder:printcolumn:name="URL",type=string,JSONPath=`.status.routeURL`
// +kubebuilder:printcolumn:name="Age",type="date",JSONPath=".metadata.creationTimestamp"

// WebApp is the Schema for the webapps API
type WebApp struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   WebAppSpec   `json:"spec,omitempty"`
	Status WebAppStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// WebAppList contains a list of WebApp
type WebAppList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []WebApp `json:"items"`
}

func init() {
	SchemeBuilder.Register(&WebApp{}, &WebAppList{})
}
