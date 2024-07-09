# Clean up

In case you may want to remove the Juju model, you should run:

```
juju remove-model tutorial --force --timeout 1s
```

If it’s the whole multipass instance that you would like to delete, you should execute this command:

```
multipass delete --purge my-vm
```

* [Give us your feedback](https://chat.charmhub.io/charmhub/channels/data-platform).
* [Contribute to the code base](https://github.com/canonical/opensearch-dashboards-opertor)