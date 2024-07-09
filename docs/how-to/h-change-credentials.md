# Change the kibanaserver password

Dashboards have a “super-user” called kibanaserver, that is in reality a specific user set in the Opensearch database.

For this reason, the credentials change doesn’t happen on the Dashboards side, rather on the Opensearch side.

Running the following command on the leader unit changes the kibanaserver password:

```
juju run openserach/0 set-password
```

The new credentials will be populated for the Dashboards charm.