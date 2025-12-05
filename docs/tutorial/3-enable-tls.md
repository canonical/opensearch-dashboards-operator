(tutorial-3-enable-tls)=
# 3. Enable TLS encryption

Charmed Opensearch Dashboards supports HTTPS connections.
Configuration is similar to what we have seen for Opensearch – we just need
to integrate the Dashboards charm against the TLS charm:

```shell
juju integrate self-signed-certificates opensearch-dashboards
```

Once the two charms are successfully related, you should be able to access the same URL now using HTTPS.
