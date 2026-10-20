# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "opensearch-dashboards-k8s"
  nullable    = false
}

variable "base" {
  description = "The base to deploy the charm on."
  type        = string
  default     = "ubuntu@24.04"
}

variable "channel" {
  description = "Charmhub channel"
  type        = string
  default     = "2/edge"
  nullable    = false
}

variable "config" {
  description = "Map of charm configuration options"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "constraints" {
  description = "Constraints for this application"
  type        = string
  default     = "arch=amd64"
}

variable "expose" {
  description = "Expose the application for external access."
  type = list(object({
    cidrs     = optional(string)
    endpoints = optional(string)
    spaces    = optional(string)
  }))
  default  = []
  nullable = false

  validation {
    condition     = length(var.expose) <= 1
    error_message = "`expose` takes at most one entry. To expose several endpoints, list them comma-separated in the entry's `endpoints` attribute."
  }
}

variable "model_uuid" {
  description = "Model UUID"
  type        = string
  nullable    = false
}

variable "offered_endpoints" {
  description = "Endpoints to expose as Juju offers for cross-model integration."
  type        = list(string)
  default     = []
  nullable    = false

  validation {
    condition     = alltrue([for endpoint in var.offered_endpoints : contains(["grafana-dashboard", "metrics-endpoint"], endpoint)])
    error_message = "`offered_endpoints` may only contain `grafana-dashboard` or `metrics-endpoint`."
  }
}

variable "resources" {
  description = "Map of the charm resources."
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "revision" {
  description = "Charm revision"
  type        = number
  default     = null
}

variable "units" {
  description = "Charm units"
  type        = number
  default     = 1
}
