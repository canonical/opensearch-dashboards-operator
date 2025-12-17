(tutorial-2-deploy)=
# 2. Get OpenSearch Dashboards up and running

The objective of Opensearch Dashboard is to display the contents of an Opensearch database.
This is why a  functional Opensearch database is a pre-requisite for the Dashboards application
to install successfully.

So, before going further, let’s set up Charmed Opensearch.
Note that Opensearch has a mandatory requirement of TLS support, so we need to deploy it
alongside the `self-signed-certificates` charm and integrate (also known as “relate”) them.

Make sure that the environment is ready and the Juju model is correctly configured following
instructions in OpenSearch Documentation
[Set kernel parameters](https://canonical-charmed-opensearch.readthedocs-hosted.com/2/tutorial/1-set-up-the-environment/#set-kernel-parameters).

Subsequently, we can deploy Opensearch with TLS:

```shell
juju deploy opensearch --channel=2/edge -n 2
juju deploy self-signed-certificates --channel=1/stable
juju integrate self-signed-certificates opensearch
```

We can simply add the Opensearch Dashboards charm to this setup by deploying and relating it to Opensearch

```shell
juju deploy opensearch-dashboards --channel=2/edge
juju integrate opensearch opensearch-dashboards
```

And there we go!
Now if you check the status of your services with `juju status`.
Your output should be similar to the example below:

```text
Model      Controller  Cloud/Region         Version  SLA          Timestamp
tutorial   overlord    localhost/localhost  3.5.3    unsupported  16:50:56+02:00

App                       Version  Status  Scale  Charm                     Channel        Rev  Exposed  Message
opensearch                         active      2  opensearch                2/edge         159  no       
opensearch-dashboards              active      1  opensearch-dashboards     2/edge          20  no       
self-signed-certificates           active      1  self-signed-certificates  1/stable  317  no       

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
```

To verify the integrations, add the flag `--relations`.

```shell
juju status --relations
```

Alternatively, if you want to monitor your system (with a view updating every second):

```shell
juju status --watch 1s
```
