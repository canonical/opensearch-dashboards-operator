(dashboard-how-to-manage-security)=
# Manage security

This guide covers enabling TLS encryption and changing the `kibanaserver`
credentials for Charmed OpenSearch Dashboards.

## Enable TLS encryption

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

For further guidance on how to manage TLS certificates, see the [TLS encryption page for the OpenSearch charm](https://canonical.com/data/opensearch/docs/2/how-to/tls-encryption/).

## Change credentials

Dashboards have a "super-user" called `kibanaserver`, that is a built-in user
set in the Opensearch database.

For this reason, the credentials change doesn't happen on the Dashboards side,
rather on the Opensearch side.

Running the following command on the leader unit changes the `kibanaserver` password:

```shell
juju run opensearch/0 set-password
```

The new credentials will be populated for the Dashboards charm.