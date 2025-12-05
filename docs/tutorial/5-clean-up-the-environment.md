(tutorial-5-clean-up-the-environment)=
# 5. Clean up the environment

In case you may want to remove the Juju model, you should run:

```shell
juju remove-model tutorial --force --timeout 1s
```

If it’s the whole Multipass instance that you would like to delete, you should execute this command:

```shell
multipass delete --purge my-vm
```

* [Give us your feedback](https://matrix.to/#/#charmhub-data-platform:ubuntu.com).
* [Contribute to the code base](https://github.com/canonical/opensearch-dashboards-operator)
