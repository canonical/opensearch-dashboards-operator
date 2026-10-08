# Terraform module for opensearch-dashboards-k8s

This is a Terraform module facilitating the deployment of the OpenSearch Dashboards K8s charm (`opensearch-dashboards-k8s`) with [Terraform juju provider](https://github.com/juju/terraform-provider-juju/). For more information, refer to the provider [documentation](https://registry.terraform.io/providers/juju/juju/latest/docs).

This module requires a `juju` Kubernetes model to be available. Refer to the [usage section](#usage) below for more details.

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
| ---- | ------- |
| terraform | >= 1.6 |
| juju | ~> 2.0 |

## Providers

| Name | Version |
| ---- | ------- |
| juju | ~> 2.0 |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| app_name | Application name | `string` | `"opensearch-dashboards-k8s"` | no |
| base | The base to deploy the charm on. | `string` | `"ubuntu@24.04"` | no |
| channel | Charmhub channel | `string` | `"2/edge"` | no |
| config | Map of charm configuration options | `map(string)` | `{}` | no |
| constraints | Constraints for this application | `string` | `"arch=amd64"` | no |
| expose | Expose the application for external access. | <pre>list(object({<br/>    cidrs     = optional(string)<br/>    endpoints = optional(string)<br/>    spaces    = optional(string)<br/>  }))</pre> | `[]` | no |
| model_uuid | Model UUID | `string` | n/a | yes |
| offered_endpoints | Endpoints to expose as Juju offers for cross-model integration. | `list(string)` | `[]` | no |
| resources | Map of the charm resources. | `map(string)` | `{}` | no |
| revision | Charm revision | `number` | `null` | no |
| units | Charm units | `number` | `1` | no |

## Outputs

| Name | Description |
| ---- | ----------- |
| application | The deployed OpenSearch Dashboards application. |
| offers | Map of all offers exposed by this application. |
| provides | Map of all `provides` endpoints. |
| requires | Map of all `requires` endpoints. |
<!-- END_TF_DOCS -->

## Usage

This module is intended to be used as part of a higher-level module. When defining one, users should ensure that Terraform is aware of the `juju_model` dependency of the charm module. There are two options to do so when creating a high-level module:

### Define a `juju_model` resource
Define a `juju_model` resource on a Kubernetes cloud and pass to the `model_uuid` input a reference to the `juju_model` resource's UUID. For example:

```
resource "juju_model" "opensearch" {
  name = "opensearch"

  cloud {
    name = "<k8s-cloud>"
  }
}

module "opensearch_dashboards" {
  source     = "<path-to-this-directory>"
  model_uuid = juju_model.opensearch.uuid
}
```

### Define a `data` source
Define a `data` source and pass to the `model_uuid` input a reference to the `data.juju_model` resource's UUID. This will enable Terraform to look for a `juju_model` resource with a name attribute equal to the one provided, and apply only if this is present. Otherwise, it will fail before applying anything.

```
data "juju_model" "opensearch" {
  name  = var.model
  owner = "admin"
}

module "opensearch_dashboards" {
  source     = "<path-to-this-directory>"
  model_uuid = data.juju_model.opensearch.uuid
}
```

### Relate to OpenSearch

OpenSearch Dashboards requires an OpenSearch cluster. Deploy one by following the description in: https://github.com/canonical/opensearch-operator/, in the `terraform/kubernetes` directory and relate both of them together:

```
resource "juju_integration" "opensearch_dashboards_opensearch" {
  model_uuid = juju_model.opensearch.uuid

  application {
    name     = module.opensearch_dashboards.requires.opensearch_client.name
    endpoint = module.opensearch_dashboards.requires.opensearch_client.endpoint
  }

  application {
    name     = module.opensearch.provides.opensearch_client.name
    endpoint = module.opensearch.provides.opensearch_client.endpoint
  }
}
```

### Add an ingress

The OpenSearch Dashboards application will remain in a `blocked` state until its `ingress` endpoint is related to an ingress provider, which this module does not deploy. Deploy one and relate it to the `ingress` endpoint. For example, with the traefik-k8s charm:

```
resource "juju_application" "traefik_k8s" {
  model_uuid = juju_model.opensearch.uuid
  trust      = true

  charm {
    name    = "traefik-k8s"
    channel = "latest/stable"
  }
}

resource "juju_integration" "opensearch_dashboards_ingress" {
  model_uuid = juju_model.opensearch.uuid

  application {
    name     = module.opensearch_dashboards.requires.ingress.name
    endpoint = module.opensearch_dashboards.requires.ingress.endpoint
  }

  application {
    name     = juju_application.traefik_k8s.name
    endpoint = "ingress"
  }
}
```

### Enable TLS

To access OpenSearch Dashboards over HTTPS, relate the ingress and TLS providers. For example, with the traefik-k8s and self-signed-certificates charms:

```
resource "juju_application" "self_signed_certificates" {
  model_uuid = juju_model.opensearch.uuid

  charm {
    name    = "self-signed-certificates"
    channel = "1/stable"
  }
}

resource "juju_integration" "traefik_k8s_tls" {
  model_uuid = juju_model.opensearch.uuid

  application {
    name     = juju_application.traefik_k8s.name
    endpoint = "certificates"
  }

  application {
    name     = juju_application.self_signed_certificates.name
    endpoint = "certificates"
  }
}
```

The optional `certificates` endpoint allows OpenSearch Dashboards to serve HTTPS to the ingress provider. Relate it to the same TLS provider as the ingress so that the ingress trusts its certificate:

```
resource "juju_integration" "opensearch_dashboards_tls" {
  model_uuid = juju_model.opensearch.uuid

  application {
    name     = module.opensearch_dashboards.requires.certificates.name
    endpoint = module.opensearch_dashboards.requires.certificates.endpoint
  }

  application {
    name     = juju_application.self_signed_certificates.name
    endpoint = "certificates"
  }
}
```
