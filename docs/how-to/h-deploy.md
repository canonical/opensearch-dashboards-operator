# Deploy the Opensearch Dashboards charm

Please follow the [Tutorial](/t/14119) for detailed instructions on how to deploy the charm on LXD.

Below is a summary of the commands:

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

juju relate  self-signed-certificates opensearch

juju deploy opensearch-dashboards --channel=2/edge
juju relate opensearch opensearch-dashboards
juju relate self-signed-certificates opensearch-dashboards   # TLS
```

As a result, a healthy system should look something like this: 

```
Model  Controller     Cloud/Region         Version  SLA          Timestamp
test   opensearchctl  localhost/localhost  3.1.8    unsupported  02:45:35+02:00

App                       Version  Status   Scale  Charm                     Channel  Rev  Exposed  Message
opensearch                         active       2  opensearch                2/edge    87  no       
opensearch-dashboards              active       1  opensearch-dashboards     2/edge     3  no       
self-signed-certificates           active       1  self-signed-certificates  stable    72  no       

Unit                         Workload  Agent  Machine  Public address  Ports  Message
opensearch-dashboards/0*     active    idle   2        10.163.9.15            
opensearch/3*                active    idle   5        10.163.9.136          
opensearch/4                 waiting   idle   6        10.163.9.36            Requesting lock on operation: start
self-signed-certificates/0*  active    idle   1        10.163.9.165           

Machine  State    Address       Inst id        Base          AZ  Message
1        started  10.163.9.165  juju-00edff-1  ubuntu@22.04      Running
2        started  10.163.9.15   juju-00edff-2  ubuntu@22.04      Running
5        started  10.163.9.136  juju-00edff-5  ubuntu@22.04      Running
6        started  10.163.9.36   juju-00edff-6  ubuntu@22.04      Running

Integration provider                   Requirer                                 Interface           Type     Message
opensearch-dashboards:dashboard_peers  opensearch-dashboards:dashboard_peers    dashboard_peers     peer     
opensearch-dashboards:restart          opensearch-dashboards:restart            rolling_op          peer     
opensearch:node-lock-fallback          opensearch:node-lock-fallback            node_lock_fallback  peer     
opensearch:opensearch-client           opensearch-dashboards:opensearch_client  opensearch_client   regular  
opensearch:opensearch-peers            opensearch:opensearch-peers              opensearch_peers    peer     
opensearch:upgrade-version-a           opensearch:upgrade-version-a             upgrade             peer     
self-signed-certificates:certificates  opensearch:certificates                  tls-certificates    regular  
```