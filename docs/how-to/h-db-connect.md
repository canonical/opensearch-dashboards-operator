# Connection to Opensearch

An essential pre-requisite for Dashboards is an Opensearch database.

Opensearch can be deployed as such:

```
juju add-model test

cat <<EOF > cloudinit-userdata.yaml
cloudinit-userdata: |
  postruncmd:
    - [ 'sysctl', '-w', 'vm.max_map_count=262144' ]
    - [ 'sysctl', '-w', 'vm.swappiness=0' ]
    - [ 'sysctl', '-w', 'net.ipv4.tcp_retries2=5' ]
    - [ 'sysctl', '-w', 'fs.file-max=1048576' ]
EOF

juju model-config --file cloudinit-userdata.yaml

juju deploy opensearch --channel=2/edge
juju deploy self-signed-certificates

juju integrate  self-signed-certificates opensearch
```

Now, on top of a live, healthy database we can deploy the visualization interface:

```
juju deploy opensearch-dashboards --channel=2/edge
```

…and integrate it with the database:

```
juju integrate opensearch opensearch-dashboards
```