# Enable TLS encryption

Charmed Opensearch Dashboads supports HTTPS connections. Configuration is similar to what we have seen for Opensearch – we just need to relate the Dashboards charm against the TLS charm:

```
juju relate self-signed-certificates opensearch-dashboards
```

Once the two charms are successfully related, you should be able to access the same URL now using HTTPS.