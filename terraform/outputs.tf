# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# integration endpoints
output "requires" {
  description = "Map of all \"requires\" endpoints"
  value = {
    opensearch_client = "opensearch-client"
    certificates      = "certificates"
  }
}

output "provides" {
  description = "Map of all \"provides\" endpoints"
  value = {
    cos_agent = "cos-agent"
  }
}

output "app_names" {
  description = "Output of all deployed application names."
  value = {
    opensearch-dashboards    = juju_application.opensearch-dashboards.name
    self-signed-certificates = var.tls ? juju_application.self-signed-certificates["deployed"].name : null
  }
}
