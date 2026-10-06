(dashboard-reference-monitoring)=
# Monitoring reference: metrics and alert rules

This reference describes the OpenSearch Dashboards metrics and alert rules available
through COS on VMs and Kubernetes. To set up COS, see
[How to enable monitoring](dashboard-how-to-enable-monitoring).

## Metrics

Both the OpenSearch Dashboards snap on VMs and the Charmed OpenSearch Dashboards rock on Kubernetes run
[the Prometheus Exporter for OpenSearch Dashboards](https://github.com/canonical/prometheus-opensearch-dashboards-exporter),
which serves metrics on port 9684 at `/metrics`.
The machine charm shares its metrics with COS through `cos-agent`.
On Kubernetes, `opensearch-dashboards-k8s` provides a `metrics-endpoint`
for Prometheus scraping, either directly or through an OpenTelemetry Collector.

For descriptions of the exporter metrics, see its
[README](https://github.com/canonical/prometheus-opensearch-dashboards-exporter?tab=readme-ov-file#metrics).

## Default alert rules

To ensure you are referencing the latest default alert rules, check the source file
for your charm variant:

* VM: [machine Prometheus alert rules](https://github.com/canonical/opensearch-dashboards-operator/blob/2/edge/machine/src/alert_rules/prometheus/prometheus_alerts.yaml)
* K8s: [Kubernetes Prometheus alert rules](https://github.com/canonical/opensearch-dashboards-operator/blob/2/edge/kubernetes/src/alert_rules/prometheus/prometheus_alerts.yaml)

The Kubernetes charm also ships [Loki log-based alert rules](https://github.com/canonical/opensearch-dashboards-operator/blob/2/edge/kubernetes/src/loki_alert_rules/dashboards_logs.rule).
Their checked-in expressions filter on `juju_application="opensearch-dashboards"`;
they will not match the default `opensearch-dashboards-k8s` application name
without changing that filter.

Both charms include these Prometheus alert rules:

```{list-table}
:header-rows: 1

* - Alert
  - Severity
  - Notes
* - OpenSearchDashboardsScrapeFailed
  - ![critical](https://img.shields.io/badge/critical-red)
  - Triggered when the prometheus scrape fails.
* - OpenSearchDashboardsRed
  - ![critical](https://img.shields.io/badge/critical-red)
  - OpenSearch Dashboards status can turn red for the following reasons:
    - Incompatibility between OpenSearch Dashboards and OpenSearch Service
    - Insufficient memory
    - OpenSearch is in red state
* - OpenSearchDashboardsYellow
  - ![warning](https://img.shields.io/badge/warning-yellow)
  - Triggered when OpenSearch Dashboards is yellow. Dashboard plugins might be degraded or shards may be relocating or initializing.
* - OpenSearchDashboardsPluginRed
  - ![critical](https://img.shields.io/badge/critical-red)
  - Triggered when OpenSearch Dashboards plugin or core component are in red state.
* - OpenSearchDashboardsPluginYellow
  - ![warning](https://img.shields.io/badge/warning-yellow)
  - Triggered when OpenSearch Dashboards plugin or core component are in yellow state.
* - OpenSearchDashboardsNoMetrics
  - ![critical](https://img.shields.io/badge/critical-red)
  - Triggered when exporter failed to collect status metrics.
* - OpenSearchDashboardsLongResponseTime
  - ![critical](https://img.shields.io/badge/critical-red)
  - Triggered when the server is up and responsive, however with a high latency.
```
