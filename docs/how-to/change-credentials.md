(how-to-change-credentials)=
# Change credentials

Dashboards have a “super-user” called `kibanaserver`, that is a built-in user
set in the Opensearch database.

For this reason, the credentials change doesn’t happen on the Dashboards side,
rather on the Opensearch side.

Running the following command on the leader unit changes the `kibanaserver` password:

```shell
juju run openserach/0 set-password
```

The new credentials will be populated for the Dashboards charm.
