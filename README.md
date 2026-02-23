# OpenSearch Dashboards Operator

[![Charmhub](https://charmhub.io/opensearch/badge.svg)](https://charmhub.io/opensearch)
[![Release](https://github.com/canonical/opensearch-dashboards-operator/actions/workflows/release.yaml/badge.svg)](https://github.com/canonical/opensearch-dashboards-operator/actions/workflows/release.yaml)
[![Tests](https://github.com/canonical/opensearch-dashboards-operator/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/canonical/opensearch-dashboards-operator/actions/workflows/ci.yaml)

## Description

[OpenSearch Dashboards](https://opensearch.org/docs/latest/dashboards/)
is a frontend application that for visualizing data stored in an OpenSearch
database. Charmed OpenSearch Dashboard is the adaptation of the
[OpenSearch Dashboards](https://opensearch.org/docs/latest/dashboards/)
user interface to the [Juju](https://juju.is/) environment.

The charm supports access via:

- HTTPS (typically for direct access)
- HTTP (load-balancing)

![OpenSearch Dashboards](./docs/resources/opensearch_dashboard.png)

## Usage

### Pre-requisites

#### Juju

OpenSearch Dashboards is a Juju charm. This means that an existing Juju environment is necessary.

Install and initialize the [LXD](https://canonical.com/lxd)
lightweight container hypervisor and Juju from the [Snap Store](https://snapcraft.io/store):

```shell
sudo snap install juju --classic --channel=3.1/stable
sudo snap install lxd
lxd init --auto
```

Then, bootstrap Juju over LXD:

```shell
juju bootstrap localhost
```

#### Charmed OpenSearch

OpenSearch Dashboards visualizes an underlying OpenSearch database.
This means that a [Charmed OpenSearch](https://charmhub.io/opensearch/)
instance also has to be ready and available.

A straightforward installation guide is available in the charm's
[Github repository](https://github.com/canonical/opensearch-operator?tab=readme-ov-file#usage).

### Install Charmed OpenSearch Dashboards

The Dashboards charm requires no specific environment adjustments.
Therefore all we need to do to deploy the charm from [Charmhub](https://charmhub.io/opensearch-dashboards) is

```shell
juju deploy opensearch-dashboards --channel=2/edge
```

and integrate it with the OpenSearch charm:

```shell
juju integrate opensearch opensearch-dashboards
```

#### Enable TLS encryption

Switching to TLS support for the OpenSearch Dashboards charms goes identically to
how it goes for OpenSearch.

Install the
[self-signed-certificates operator](https://github.com/canonical/self-signed-certificates-operator)

```shell
juju deploy self-signed-certificates --channel=1/stable
```

and integrate it with the Dashboards charm

```shell
juju integrate opensearch-dashboards self-signed-certificates
```

### Test interactive access

Functionality of the service can be tested by making an attempt to access the
portal either from the command-line or a web browser.

A few pieces of information are required to do this.

#### URL

Construct the URL first.

The Dashboard front-end is exposed on port `5601`. Using `juju status` we can
retrieve the IP of each unit:

```shell
opensearch-dashboards/0*     active    idle   1        10.4.151.209              
```

Using the example above, the Dashboard URL is `http://10.4.151.209:5601`.

#### Authentication

Set up a database user by deploying the `data-integrator` [charm](https://charmhub.io/data-integrator)
and integrating it with `opensearch`. The user is created automatically as a result of the integration.

```shell
juju deploy data-integrator --config index-name=<index_name>
juju integrate data-integrator opensearch
```

Retrieve user credentials running

```shell
juju run data-integrator/0 get-credentials
```

at the bottom of the output you should see something like:

```text
  password: 8kubD7nbWYZFHPVEzIVmTyqV42I7wHb4
  <CA certificate here>
  username: opensearch-client_15
```

### Access the Dashboard

Using information from above, the dashboard URI is constructed as

```text
https://<IP>:5601
```

Log in with the credentials of the new user.

![OpenSearch Dashboards login](./docs/resources/opensearch_dashboard_login.png)

You must create an "index pattern" that enables the Dasboard to access the user's data.
It should specify the `index_name` that was used to create the user with `data-integrator`.

Follow instructions from OpenSearch documentation on
[How to create an index pattern](https://opensearch.org/docs/latest/dashboards/management/index-patterns/#creating-an-index-pattern)

When the index pattern is defined, data that belongs to the user will display in the Dashboards.

## License

The Charmed OpenSearch Dashboards Operator is free software, distributed under the Apache
Software License, version 2.0. See [LICENSE](./LICENSE) for more information.
