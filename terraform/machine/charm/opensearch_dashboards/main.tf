# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

resource "juju_application" "opensearch_dashboards" {
  charm {
    name     = "opensearch-dashboards"
    channel  = var.channel
    revision = var.revision
    base     = var.base
  }
  config            = var.config
  constraints       = var.constraints
  endpoint_bindings = var.endpoint_bindings
  machines          = length(var.machines) == 0 ? null : var.machines
  model_uuid        = var.model_uuid
  name              = var.app_name
  units             = length(var.machines) == 0 ? var.units : null

  dynamic "expose" {
    for_each = var.expose

    content {
      cidrs     = expose.value.cidrs
      endpoints = expose.value.endpoints
      spaces    = expose.value.spaces
    }
  }
}
