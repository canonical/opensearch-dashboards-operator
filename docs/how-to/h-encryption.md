# TLS support

First, deploy the  self-signed-certificates charm:

```
juju deploy self-signed-certificates --config ca-common-name="Tutorial CA"
``````````````````````

Then,  relate it to the Opensearch Dashboards charm.

```
juju relate self-signed-certificates opensearch-dashboards
```