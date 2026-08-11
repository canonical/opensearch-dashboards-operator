(dashboard-reference-monitoring)=
# Monitoring reference: metrics and alert rules

This reference describes the metrics exposed by the OpenSearch Dashboards Prometheus exporter and lists the default alert rules shipped with the charm.

## Metrics

The Prometheus exporter is automatically installed by the OpenSearch Dashboards snap using:
[The Prometheus Exporter for OpenSearch Dashboards](https://github.com/canonical/prometheus-opensearch-dashboards-exporter).

The meaning of the metrics collected can be found in the
[README](https://github.com/canonical/prometheus-opensearch-dashboards-exporter?tab=readme-ov-file#metrics)
of the exporter.

To ensure you are referencing the latest default alert rules, check the source file
of alert definitions in the repository's
[prometheus_alerts.yaml](https://github.com/canonical/opensearch-dashboards-operator/blob/2/edge/machine/src/alert_rules/prometheus/prometheus_alerts.yaml)
file.

## Default alert rules

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
  - ![warning](https://img.shields.io/badge/critical-red)
  - Triggered when exporter failed to collect status metrics.
* - OpenSearchDashboardsLongResponseTime
  - ![high](https://img.shields.io/badge/critical-red)
  - Triggered when the server is up and responsive, however with a high latency.
```
