# Scale up/down the application units

It’s very easy to increase or decrease the number of units in a Juju system.

Scaling up goes as:

```
juju add-unit opensearch-dashboards -n <desired_num_of_units>
```

While scaling down goes as: 

```
juju remove-unit opensearch-dashboards/<ID>
```