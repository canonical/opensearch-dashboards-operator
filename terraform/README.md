# Terraform module for opensearch-dashboards-operator

This is a Terraform module facilitating the deployment of the OpenSearch charm with [Terraform juju provider](https://github.com/juju/terraform-provider-juju/). For more information, refer to the provider [documentation](https://registry.terraform.io/providers/juju/juju/latest/docs). 

## Requirements
This module requires a `juju` model to be available. Refer to the [usage section](#usage) below for more details.

## API

### Inputs
The module offers the following configurable inputs:

| Name          | Type        | Description                                     | Required   |
|---------------|-------------|-------------------------------------------------|------------|
| `app_name`    | string      | Application name                                | False      |
| `channel`     | string      | Channel that the charm is deployed from         | False      |
| `base`        | string      | The series to be used for this charm            | False      |
| `config`      | map(string) | Map of the charm configuration options          | False      |
| `model`       | string      | Name of the model that the charm is deployed on | **True**   |
| `resources`   | map(string) | Map of the charm resources                      | False      |
| `revision`    | number      | Revision number of the charm name               | False      |
| `units`       | number      | Number of units to be deployed                  | False      |
| `constraints` | string      | Machine constraints for the charm               | False      |
| `tls`         | bool        | Whether TLS should be enabled                   | False      |
| `expose`      | bool        | If set to true, opens to anyone's access        | False      |


### Outputs
When applied, the module exports the following outputs:

| Name       | Description                 |
|------------|-----------------------------|
| `app_name` | Application name            |
| `provides` | Map of `provides` endpoints |
| `requires` | Map of `requires` endpoints |

## Usage

This module is intended to be used as part of a higher-level module. When defining one, users should ensure that Terraform is aware of the `juju_model` dependency of the charm module. There are two options to do so when creating a high-level module:

### Define a `juju_model` resource
Define a `juju_model` resource and pass to the `model` input a reference to the `juju_model` resource's name. For example:

```
resource "juju_model" "opensearch" {
  name = opensearch
}

module "opensearch-dashboards" {
  source = "<path-to-this-directory>"
  model = juju_model.opensearch.name
}
```

### Define a `data` source
Define a `data` source and pass to the `model` input a reference to the `data.juju_model` resource's name. This will enable Terraform to look for a `juju_model` resource with a name attribute equal to the one provided, and apply only if this is present. Otherwise, it will fail before applying anything.

```
data "juju_model" "opensearch" {
  name = var.model
}

module "opensearch-dashboards" {
  source = "<path-to-this-directory>"
  model = data.juju_model.opensearch.name
}
```

### Deploy OpenSearch Module and Relate

Follow the description in: https://github.com/canonical/opensearch-operator/, in the `terraform` directory. Deploy an opensearch
cluster and relate both of them together:

```
module "opensearch" {
  ...
}

resource "juju_integration" "opensearch-and-dashboard" {
  model = juju_model.opensearch.name

  application {
    name     = module.opensearch.app_name
    endpoint = module.opensearch.opensearch_client_endpoint
  }

  application {
    name     = module.opensearch-dashboards.app_name
    endpoint = module.opensearch-dashboards.opensearch_client_endpoint
  }
}
```
