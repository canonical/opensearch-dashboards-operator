(how-to-enable-tls)=
# Enable TLS

First, deploy the self-signed-certificates charm:

```shell
juju deploy self-signed-certificates --config ca-common-name="Tutorial CA"
```

Then, relate it to the Opensearch Dashboards charm.

```shell
juju relate self-signed-certificates opensearch-dashboards
```
