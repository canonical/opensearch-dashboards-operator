# Terraform module for opensearch-dashboards

This is a Terraform module facilitating the deployment of the OpenSearch Dashboards charm with [Terraform juju provider](https://github.com/juju/terraform-provider-juju/). For more information, refer to the provider [documentation](https://registry.terraform.io/providers/juju/juju/latest/docs).

This module requires a `juju` model to be available. Refer to the [usage section](#usage) below for more details.

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
| app_name | Application name | `string` | `"opensearch-dashboards"` | no |
| base | The base to deploy the charm on. | `string` | `"ubuntu@24.04"` | no |
| channel | Charmhub channel | `string` | `"2/edge"` | no |
| config | Map of charm configuration options | `map(string)` | `{}` | no |
| constraints | Machine constraints for this application | `string` | `"arch=amd64"` | no |
| endpoint_bindings | Set of endpoint bindings | <pre>set(object({<br/>    space    = string<br/>    endpoint = optional(string)<br/>  }))</pre> | `[]` | no |
| expose | Expose the application for external access. | <pre>list(object({<br/>    cidrs     = optional(string)<br/>    endpoints = optional(string)<br/>    spaces    = optional(string)<br/>  }))</pre> | `[]` | no |
| machines | List of machines for placement. When set, one unit is deployed on each listed machine. | `set(string)` | `[]` | no |
| model_uuid | Model UUID | `string` | n/a | yes |
| revision | Charm revision | `number` | `null` | no |
| units | Charm units. Ignored when `machines` is set. | `number` | `1` | no |

## Outputs

| Name | Description |
| ---- | ----------- |
| application | The deployed OpenSearch Dashboards application. |
| offers | No offers are exposed by this application. |
| provides | Map of all `provides` endpoints. |
| requires | Map of all `requires` endpoints. |
<!-- END_TF_DOCS -->

## Usage

This module is intended to be used as part of a higher-level module. When defining one, users should ensure that Terraform is aware of the `juju_model` dependency of the charm module. There are two options to do so when creating a high-level module:

### Define a `juju_model` resource
Define a `juju_model` resource and pass to the `model_uuid` input a reference to the `juju_model` resource's UUID. For example:

```
resource "juju_model" "opensearch" {
  name = "opensearch"
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

OpenSearch Dashboards requires an OpenSearch cluster. Deploy one with the OpenSearch Terraform modules from https://github.com/canonical/opensearch-operator/, in the `terraform` directory, and relate both of them together:

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

### Enable TLS

The optional `certificates` endpoint allows browsers to connect to OpenSearch Dashboards over HTTPS. This module does not deploy a TLS provider. To enable TLS, deploy a TLS provider and relate it to the `certificates` endpoint. For example, with the self-signed-certificates charm:

```
resource "juju_application" "self_signed_certificates" {
  model_uuid = juju_model.opensearch.uuid

  charm {
    name    = "self-signed-certificates"
    channel = "1/stable"
  }
}

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
