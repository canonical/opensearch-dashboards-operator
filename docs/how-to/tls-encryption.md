(dashboard-how-to-enable-tls)=
# How to manage TLS encryption

First, make sure you have your TLS certificates provider set up.

This guide will show how to enable TLS using the
[`self-signed-certificates` operator](https://github.com/canonical/self-signed-certificates-operator)
as an example.

```{caution}
**[Self-signed certificates](https://en.wikipedia.org/wiki/Self-signed_certificate)
are not recommended for a production environment.**

Check the [X.509 certificates topic](https://charmhub.io/topics/security-with-x-509-certificates)
for an overview of the signed and self-signed certificate charms available.
```

To deploy the `self-signed-certificates` charm:

```shell
juju deploy self-signed-certificates --config ca-common-name="Tutorial CA"
```

Then, relate it to the Opensearch Dashboards charm.

```shell
juju relate self-signed-certificates opensearch-dashboards
```
