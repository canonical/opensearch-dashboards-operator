(dashboard-how-to-manage-tls)=
# How to manage TLS encryption

First, make sure you have a TLS certificates charm set up.

This guide will show how to enable TLS using the
[`self-signed-certificates` charm](https://github.com/canonical/self-signed-certificates-operator)
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

Then, integrate it with the OpenSearch Dashboards charm:

```shell
juju integrate self-signed-certificates opensearch-dashboards
```
