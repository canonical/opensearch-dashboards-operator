# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "opensearch-dashboards"
  nullable    = false
}

variable "base" {
  description = "Charm base (old name: series)"
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
  description = "Machine constraints for this application"
  type        = string
  default     = "arch=amd64"
}

variable "endpoint_bindings" {
  description = "Set of endpoint bindings"
  type = set(object({
    space    = string
    endpoint = optional(string)
  }))
  default  = []
  nullable = false
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
}

variable "machines" {
  description = "List of machines for placement. When set, one unit is deployed on each listed machine."
  type        = set(string)
  default     = []
  nullable    = false
}

variable "model_uuid" {
  description = "Model UUID"
  type        = string
  nullable    = false
}

variable "revision" {
  description = "Charm revision"
  type        = number
  default     = null
}

variable "units" {
  description = "Charm units. Ignored when `machines` is set."
  type        = number
  default     = 1
}
