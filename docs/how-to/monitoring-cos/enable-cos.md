(dashboard-how-to-monitoring-enable-cos)=
# How to enable monitoring (COS)

```{note}
All commands are written for juju >= v.3.1.7
```

## Prerequisites

* A deployed [Charmed OpenSearch operator with a Charmed Opensearch Dashboards operator](dashboards-deploy)
* A deployed [`cos-lite` bundle in a Kubernetes environment](https://charmhub.io/topics/canonical-observability-stack/tutorials/install-microk8s)

## Offer interfaces via the COS controller

First, we will switch to the COS K8s environment and offer COS interfaces to be cross-model
integrated with the Charmed OpenSearch model.

To switch to the Kubernetes controller for the COS model, run

```shell
juju switch <k8s_cos_controller>:<cos_model_name>
```

To offer the COS interfaces, run

```shell
juju offer grafana:grafana-dashboard
juju offer loki:logging
juju offer prometheus:receive-remote-write
```

## Consume offers via the OpenSearch Dashboards model

Next, we will switch to the Charmed OpenSearch Dashboards model, find offers, and consume them.

We are currently on the Kubernetes controller for the COS model.
To switch to the OpenSearch Dashboards model, run

```shell
juju switch <db_controller>:<opensearch_dashboards_model_name>
```

To consume offers to be reachable in the current model, run

```shell
juju consume <k8s_cos_controller>:admin/cos.grafana
juju consume <k8s_cos_controller>:admin/cos.loki
juju consume <k8s_cos_controller>:admin/cos.prometheus
```

## Deploy and integrate Grafana

First, deploy [grafana-agent](https://charmhub.io/grafana-agent):

```shell
juju deploy grafana-agent
```

Then integrate `grafana-agent` with consumed COS offers:

```shell
juju integrate grafana-agent grafana
juju integrate grafana-agent loki
juju integrate grafana-agent prometheus
```

Finally integrate (previously known as
[relate](https://documentation.ubuntu.com/juju/3.6/reference/relation/))
it with Charmed OpenSearch Dashboards:

```shell
juju integrate grafana-agent-k8s opensearch-dashboards
```

After the integration is complete, Grafana will show the new dashboard
`Charmed OpenSearch Dashboards` and will allow access to Charmed OpenSearch Dashboards logs on Loki.

## Connect to the Grafana web interface

To connect to the Grafana web interface, follow the
[Browse dashboards](https://charmhub.io/topics/canonical-observability-stack/tutorials/install-microk8s#heading--browse-dashboards)
section of the MicroK8s "Getting started" guide.

You can obtain the admin password as follows:

```shell
juju run grafana/leader get-admin-password --model <k8s_cos_controller>:<cos_model_name>
```
