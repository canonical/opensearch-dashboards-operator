# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

resource "juju_application" "opensearch-dashboards" {

  charm {
    name     = "opensearch-dashboards"
    channel  = var.channel
    revision = var.revision
    base     = var.base
  }
  config      = var.config
  model       = var.model
  name        = var.app_name
  units       = var.units
  constraints = var.constraints

  # TODO: uncomment once final fixes have been added for:
  # Error: juju/terraform-provider-juju#443, juju/terraform-provider-juju#182
  # placement = join(",", var.machines)

  endpoint_bindings = [
    for k, v in var.endpoint_bindings : {
      endpoint = k, space = v
    }
  ]
}

# Deploy the self-signed-certificates operator if tls enabled
resource "juju_application" "self-signed-certificates" {
  for_each = var.tls ? { "deployed" = true } : {}

  model = var.model

  charm {
    name     = "self-signed-certificates"
    channel  = var.self-signed-certificates.channel
    revision = var.self-signed-certificates.revision
    base     = var.self-signed-certificates.base
  }
  constraints = var.self-signed-certificates.constraints
  config      = var.self-signed-certificates.config

  placement = length(var.self-signed-certificates.machines) == 1 ? var.self-signed-certificates.machines[0] : null
}

# Integrate with the self-signed-certificates if tls is enabled
resource "juju_integration" "tls-opensearch_dashboards_integration" {
  for_each = var.tls ? { "deployed" = true } : {}

  model = var.model

  application {
    name = juju_application.self-signed-certificates["deployed"].name
  }

  application {
    name = juju_application.opensearch-dashboards.name
  }

  depends_on = [
    juju_application.opensearch-dashboards,
    juju_application.self-signed-certificates,
  ]
}
