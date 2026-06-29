(dashboard-how-to-deploy-connect-scale)=
# How to deploy, connect, and scale

This guide covers deploying the OpenSearch Dashboards charm, connecting it to an
OpenSearch cluster, and scaling the number of units up or down.

## Prerequisites

A Juju model containing:

* An active `opensearch` application
* A TLS certificate provider charm (e.g. `self-signed-certificates`)
  integrated with `opensearch`

To learn how to set up and deploy an OpenSearch application, see steps 1, 2, and 3 of the
[OpenSearch Tutorial](https://canonical-charmed-opensearch.readthedocs-hosted.com/2/tutorial/1-set-up-the-environment/).

Make sure you've set up the correct
[kernel parameters](https://canonical-charmed-opensearch.readthedocs-hosted.com/2/tutorial/1-set-up-the-environment/#set-kernel-parameters)
for your OpenSearch deployment.

For a detailed walk-through of a full deployment on LXD, see the
[Tutorial](dashboards-tutorial).

## Deploy OpenSearch Dashboards

On top of a live, healthy OpenSearch database, deploy the Dashboards visualization interface:

```shell
juju deploy opensearch-dashboards --channel=2/edge
```

## Connect to OpenSearch

Integrate the Dashboards charm with the OpenSearch database:

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

## Scale up/down

It's very easy to increase or decrease the number of units in a Juju system.

Scaling up goes as:

```shell
juju add-unit opensearch-dashboards -n <desired_num_of_units>
```

While scaling down goes as:

```shell
juju remove-unit opensearch-dashboards/<ID>