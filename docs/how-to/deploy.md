(dashboard-how-to-deploy)=
# Deploy the Opensearch Dashboards charm

Please follow the [Tutorial](dashboards-tutorial) for detailed instructions on
how to deploy the charm on LXD.

Below is a summary of the commands (assuming that instructions from OpenSearch Documentation
[Set kernel parameters](https://canonical-charmed-opensearch.readthedocs-hosted.com/2/tutorial/1-set-up-the-environment/#set-kernel-parameters)
were applied):

```shell
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

juju deploy opensearch --channel=2/edge --config profile="testing"
juju deploy self-signed-certificates

juju relate  self-signed-certificates opensearch

juju deploy opensearch-dashboards --channel=2/edge
juju relate opensearch opensearch-dashboards
juju relate self-signed-certificates opensearch-dashboards
```

As a result, a healthy system should look something like this:

```text
Model      Controller  Cloud/Region         Version  SLA          Timestamp
tutorial   overlord    localhost/localhost  3.5.3    unsupported  17:40:00+02:00

App                       Version  Status  Scale  Charm                     Channel        Rev  Exposed  Message
opensearch                         active      2  opensearch                2/edge         159  no       
opensearch-dashboards              active      1  opensearch-dashboards     2/edge          20  no       
self-signed-certificates           active      1  self-signed-certificates 1/stable  317  no       

Unit                         Workload  Agent  Machine  Public address  Ports     Message
opensearch-dashboards/0*     active    idle   3        10.34.169.173   5601/tcp  
opensearch/0                 active    idle   0        10.34.169.84    9200/tcp  
opensearch/1*                active    idle   1        10.34.169.242   9200/tcp  
self-signed-certificates/0*  active    idle   2        10.34.169.5               

Machine  State    Address        Inst id        Base          AZ  Message
0        started  10.34.169.84   juju-df6483-0  ubuntu@22.04      Running
1        started  10.34.169.242  juju-df6483-1  ubuntu@22.04      Running
2        started  10.34.169.5    juju-df6483-2  ubuntu@22.04      Running
3        started  10.34.169.173  juju-df6483-3  ubuntu@22.04      Running

Integration provider                   Requirer                                 Interface           Type     Message
opensearch-dashboards:dashboard_peers  opensearch-dashboards:dashboard_peers    dashboard_peers     peer     
opensearch-dashboards:restart          opensearch-dashboards:restart            rolling_op          peer     
opensearch-dashboards:upgrade          opensearch-dashboards:upgrade            upgrade             peer     
opensearch:node-lock-fallback          opensearch:node-lock-fallback            node_lock_fallback  peer     
opensearch:opensearch-client           opensearch-dashboards:opensearch-client  opensearch_client   regular  
opensearch:opensearch-peers            opensearch:opensearch-peers              opensearch_peers    peer     
opensearch:upgrade-version-a           opensearch:upgrade-version-a             upgrade             peer     
self-signed-certificates:certificates  opensearch-dashboards:certificates       tls-certificates    regular  
self-signed-certificates:certificates  opensearch:certificates                  tls-certificates    regular 
```
