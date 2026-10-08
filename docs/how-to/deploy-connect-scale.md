(dashboard-how-to-deploy-connect-scale)=
# How to deploy, connect, and scale

This guide covers deploying the OpenSearch Dashboards charm, connecting it to an
OpenSearch cluster, and scaling the number of units up or down.

## Prerequisites

`````{tab-set}
---
sync-group: substrate
---
````{tab-item} VM
:sync: vm

A Juju model containing:

* An active `opensearch` application
* A TLS certificate provider charm (e.g. `self-signed-certificates`)
  integrated with `opensearch`

To learn how to set up and deploy an OpenSearch application, see steps 1, 2, and 3 of the
[OpenSearch Tutorial](https://canonical.com/data/opensearch/docs/2/tutorial/1-set-up-the-environment/).

Make sure you've set up the correct
[kernel parameters](https://canonical.com/data/opensearch/docs/2/tutorial/1-set-up-the-environment/#set-kernel-parameters)
for your OpenSearch deployment.

For a detailed walk-through of a full deployment on LXD, see the
[Tutorial](dashboards-tutorial).
````

````{tab-item} K8s
:sync: k8s

A Juju model on a Kubernetes cloud containing:

* An active `opensearch-k8s` application
* A TLS certificate provider charm (e.g. `self-signed-certificates`)
  integrated with `opensearch-k8s`

OpenSearch Dashboards requires an [ingress provider](dashboard-how-to-deploy-ingress)
such as `traefik-k8s`, which needs a load balancer for its external IP address, for example
the Canonical Kubernetes [`load-balancer`](https://documentation.ubuntu.com/canonical-kubernetes/latest/snap/howto/networking/default-loadbalancer/) feature.

To learn how to set up and deploy OpenSearch on Kubernetes, including setting the required
kernel parameters on every node, see the
[OpenSearch deploy guide](https://canonical.com/data/opensearch/docs/2/how-to/deploy/standard/).

````
`````

## Deploy OpenSearch Dashboards

On top of a live, healthy OpenSearch database, deploy the Dashboards visualization interface:

`````{tab-set}
---
sync-group: substrate
---
````{tab-item} VM
:sync: vm

```shell
juju deploy opensearch-dashboards --channel 2/edge
```
````

````{tab-item} K8s
:sync: k8s

```shell
juju deploy opensearch-dashboards-k8s --channel 2/edge --trust
```
````
`````

## Connect to OpenSearch

Integrate the Dashboards charm with the OpenSearch database:

`````{tab-set}
---
sync-group: substrate
---
````{tab-item} VM
:sync: vm

```shell
juju integrate opensearch opensearch-dashboards
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
````

````{tab-item} K8s
:sync: k8s

```shell
juju integrate opensearch-k8s opensearch-dashboards-k8s
```

OpenSearch Dashboards will remain `blocked` with `Ingress relation missing` until you
[integrate an ingress provider](dashboard-how-to-deploy-ingress).
````
`````

(dashboard-how-to-deploy-ingress)=
## Expose with ingress

`````{tab-set}
---
sync-group: substrate
---
````{tab-item} VM
:sync: vm

No ingress is needed on VMs.
````

````{tab-item} K8s
:sync: k8s

Deploy [`traefik-k8s`](https://charmhub.io/traefik-k8s) and integrate it with OpenSearch Dashboards:

```shell
juju deploy traefik-k8s --channel latest/stable --trust
juju integrate opensearch-dashboards-k8s traefik-k8s
```

As a result, a healthy system should look something like this:

```text
Model       Controller      Cloud/Region  Version  SLA          Timestamp
dashboards  opensearch-k8s  ck8s          3.6.28   unsupported  06:14:54+01:00

App                        Version  Status  Scale  Charm                      Channel        Rev  Address         Exposed  Message
opensearch-dashboards-k8s  2.19.6   active      1  opensearch-dashboards-k8s  2/edge          10  10.152.183.182  no
opensearch-k8s                      active      2  opensearch-k8s             2/edge          22  10.152.183.193  no
self-signed-certificates            active      1  self-signed-certificates   1/stable       586  10.152.183.183  no
traefik-k8s                2.11.49  active      1  traefik-k8s                latest/stable  377  10.152.183.194  no       Serving at http://192.168.68.242

Unit                          Workload  Agent  Address     Ports  Message
opensearch-dashboards-k8s/0*  active    idle   10.1.0.123
opensearch-k8s/0*             active    idle   10.1.0.77
opensearch-k8s/1              active    idle   10.1.0.35
self-signed-certificates/0*   active    idle   10.1.0.101
traefik-k8s/0*                active    idle   10.1.0.113         Serving at http://192.168.68.242

Integration provider                       Requirer                                     Interface           Type     Message
opensearch-dashboards-k8s:dashboard_peers  opensearch-dashboards-k8s:dashboard_peers    dashboard_peers     peer
opensearch-dashboards-k8s:restart          opensearch-dashboards-k8s:restart            rolling_op          peer
opensearch-dashboards-k8s:status-peers     opensearch-dashboards-k8s:status-peers       status-peers        peer
opensearch-dashboards-k8s:upgrade          opensearch-dashboards-k8s:upgrade            upgrade             peer
opensearch-k8s:node-lock-fallback          opensearch-k8s:node-lock-fallback            node_lock_fallback  peer
opensearch-k8s:opensearch-client           opensearch-dashboards-k8s:opensearch-client  opensearch_client   regular
opensearch-k8s:opensearch-peers            opensearch-k8s:opensearch-peers              opensearch_peers    peer
opensearch-k8s:status-peers                opensearch-k8s:status-peers                  status-peers        peer
opensearch-k8s:upgrade-version-a           opensearch-k8s:upgrade-version-a             upgrade             peer
self-signed-certificates:certificates      opensearch-k8s:certificates                  tls-certificates    regular
traefik-k8s:ingress                        opensearch-dashboards-k8s:ingress            ingress             regular
traefik-k8s:peers                          traefik-k8s:peers                            traefik_peers       peer
```

By default, Traefik serves the OpenSearch Dashboards URL over HTTP. To serve it over
HTTPS, integrate Traefik with a TLS provider:

```shell
juju integrate traefik-k8s self-signed-certificates:certificates
```

This encrypts traffic between Traefik and clients. To also encrypt traffic to
OpenSearch Dashboards, [enable TLS](dashboard-how-to-manage-security) on it.
Traefik must trust the CA that signs the OpenSearch Dashboards certificate.

Get the OpenSearch Dashboards URL:

```shell
juju run traefik-k8s/0 show-proxied-endpoints
```
````
`````

## Scale up/down

It's very easy to increase or decrease the number of units in a Juju system.

`````{tab-set}
---
sync-group: substrate
---
````{tab-item} VM
:sync: vm

Scaling up goes as:

```shell
juju add-unit opensearch-dashboards -n <num_units_to_add>
```

While scaling down goes as:

```shell
juju remove-unit opensearch-dashboards/<unit_number>
```
````

````{tab-item} K8s
:sync: k8s

Scale the application to the desired number of units:

```shell
juju scale-application opensearch-dashboards-k8s <desired_num_of_units>
```
````
`````
