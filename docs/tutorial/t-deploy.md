#  Get OpenSearch Dashboards up and running

The objective of Opensearch Dashboard is to display the contents of an Opensearch database. This is why a  functional Opensearch database is a pre-requisite for the Dashboards application to install successfully.

So, before going further,  let’s set up Charmed Opensearch. Note that Opensearch has a mandatory requirement of TLS support, so we need to deploy it alongside the self-signed-certificates charm and integrate (also known as “relate”) them.

First, set up a cloud-init YAML and configure the juju model:

```
# Configure the model
cat <<EOF > cloudinit-userdata.yaml
cloudinit-userdata: |
  postruncmd:
    - [ 'sysctl', '-w', 'vm.max_map_count=262144' ]
    - [ 'sysctl', '-w', 'vm.swappiness=0' ]
    - [ 'sysctl', '-w', 'net.ipv4.tcp_retries2=5' ]
    - [ 'sysctl', '-w', 'fs.file-max=1048576' ]
EOF

juju model-config --file cloudinit-userdata.yaml
```

We can deploy Opensearch with TLS:

```
juju deploy opensearch --channel=2/edge
juju deploy self-signed-certificates
juju relate  self-signed-certificates opensearch
```

We can simply add the Opensearch Dashboards charm to this setup by deploying and relating it to Opensearch

```
juju deploy opensearch-dashboards --channel=2/edge
juju relate opensearch opensearch-dashboards
```

And there we go!
Now if you check the status of your services with `juju status`. 
Your output should be similar to the example below:

```
Model  Controller     Cloud/Region         Version  SLA          Timestamp
test   opensearchctl  localhost/localhost  3.1.8    unsupported  23:40:32+02:00

App                       Version  Status  Scale  Charm                     Channel  Rev  Exposed  Message
opensearch                         active      1  opensearch                2/edge    87  no       
opensearch-dashboards              active      1  opensearch-dashboards     2/edge     3  no       
self-signed-certificates           active      1  self-signed-certificates  stable    72  no       

Unit                         Workload  Agent  Machine  Public address  Ports     Message
opensearch-dashboards/0*     active    idle   2        10.163.9.173              
opensearch/0*                active    idle   0        10.163.9.214    9200/tcp  
self-signed-certificates/0*  active    idle   1        10.163.9.76               

Machine  State    Address       Inst id        Base          AZ  Message
0        started  10.163.9.214  juju-148a0e-0  ubuntu@22.04      Running
1        started  10.163.9.76   juju-148a0e-1  ubuntu@22.04      Running
2        started  10.163.9.173  juju-148a0e-2  ubuntu@22.04      Running
```

**Note**: in case you would like to verify the integrations as well, you can add the flag `--relations`.
```
$ juju status --relations
```

Alternatively, if you want to monitor your system (with a view updating every second):

```
$ juju status --watch 1s
```