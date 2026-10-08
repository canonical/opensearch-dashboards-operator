# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

output "application" {
  description = "The deployed OpenSearch Dashboards application."
  value       = juju_application.opensearch_dashboards_k8s
}

output "offers" {
  description = "Map of all offers exposed by this application."
  value = {
    for endpoint, offer in juju_offer.offered_endpoints : replace(endpoint, "-", "_") => {
      kind = "offer"
      url  = offer.url
    }
  }
}

output "provides" {
  description = "Map of all `provides` endpoints."
  value = {
    grafana_dashboard = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards_k8s.name
      endpoint = "grafana-dashboard"
    }
    metrics_endpoint = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards_k8s.name
      endpoint = "metrics-endpoint"
    }
  }
}

output "requires" {
  description = "Map of all `requires` endpoints."
  value = {
    certificates = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards_k8s.name
      endpoint = "certificates"
    }
    ingress = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards_k8s.name
      endpoint = "ingress"
    }
    jwt_configuration = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards_k8s.name
      endpoint = "jwt-configuration"
    }
    logging = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards_k8s.name
      endpoint = "logging"
    }
    oauth = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards_k8s.name
      endpoint = "oauth"
    }
    opensearch_client = {
      kind     = "endpoint"
      name     = juju_application.opensearch_dashboards_k8s.name
      endpoint = "opensearch-client"
    }
  }
}
