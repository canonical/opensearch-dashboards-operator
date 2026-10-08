# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

output "application" {
  description = "The deployed OpenSearch Dashboards application."
  value       = juju_application.opensearch_dashboards
}

output "offers" {
  description = "No offers are exposed by this application."
  value       = {}
}

output "provides" {
  description = "Map of all `provides` endpoints."
  value = {
    cos_agent = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards.name
      endpoint = "cos-agent"
    }
  }
}

output "requires" {
  description = "Map of all `requires` endpoints."
  value = {
    certificates = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards.name
      endpoint = "certificates"
    }
    jwt_configuration = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards.name
      endpoint = "jwt-configuration"
    }
    oauth = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards.name
      endpoint = "oauth"
    }
    opensearch_client = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards.name
      endpoint = "opensearch-client"
    }
  }
}
