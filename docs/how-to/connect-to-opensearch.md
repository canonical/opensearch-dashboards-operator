(dashboard-how-to-connect-to-opensearch)=
# Connect to OpenSearch

This guide explains how to connect OpenSearch Dashboards with OpenSearch via Juju integrations.

## Prerequisites

A Juju model containing:

* An active `opensearch` application
* A TLS certificate provider charm (e.g. `self-signed-certificates`)
 integrated with `opensearch`

To learn how to set up and deploy an OpenSearch application, see steps 1, 2, and 3 of the
[OpenSearch Tutorial](https://canonical-charmed-opensearch.readthedocs-hosted.com/2/tutorial/1-set-up-the-environment/).

## Deploy and integrate

On top of a live, healthy OpenSearch database, we can deploy the Dashboards visualization interface:

```shell
juju deploy opensearch-dashboards --channel=2/edge
```

…and integrate it with the database:

```shell
juju integrate opensearch opensearch-dashboards
```

```{note}
Make sure you've set up the correct [kernel parameters](https://canonical-charmed-opensearch.readthedocs-hosted.com/2/tutorial/1-set-up-the-environment/#set-kernel-parameters) for your OpenSearch deployment.
```
