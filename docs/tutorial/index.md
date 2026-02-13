(dashboards-tutorial)=
# Tutorial

This tutorial guides you through how to get Charmed Opensearch Dashboards up and running.
It also provides a quick introduction to the following:

* Set up an environment using [Multipass](https://multipass.run/) with
[LXD](https://ubuntu.com/lxd) and [Juju](https://juju.is/).
* Deploy Opensearch Dashboards using a single command.
* Configure TLS certificate equally simple.

This tutorial focuses on Opensearch Dashboards deployment, assuming that you have familiarity with:

* Basic terminal commands.
* Opensearch and Opensearch Dashboards concepts
* The [Charmed Opensearch Operator](https://charmhub.io/opensearch)

(dashboards-setup-environment)=
## Set up the environment

In this section, you will set up your environment by:

* installing and setting up Multipass
* installing Juju and bootstrapping LXD
* setting up a graphical interface with Multipass

(dashboards-install-multipass)=
### Install and set up Multipass

[Multipass](https://multipass.run/) is a quick and easy way to launch virtual machines
running Ubuntu.
It uses the "[cloud-init](https://cloud-init.io/)" standard to install and configure
all the necessary parts automatically.

Installation of Multipass from [Snap](https://snapcraft.io/multipass) and launching a new VM using
"[charm-dev](https://github.com/canonical/multipass-blueprints/blob/main/v1/charm-dev.yaml)"
cloud-init config goes as:

```shell
sudo snap install multipass && \

multipass launch --cpus 4 --memory 8G --disk 30G --name my-vm charm-dev # tune CPU/RAM/HDD accordingly to your needs
```

The full set of launch parameters is described in the
[launch command reference](https://multipass.run/docs/launch-command).

Multipass [commands](https://multipass.run/docs/multipass-cli-commands)
are generally short and intuitive. For example, to show all running VMs:

```shell
multipass list
```

When the new VM is up and running, connect using:

```shell
multipass shell my-vm
```

You can exit the Multipass VM using `Ctrl + D` or the exit command.

(dashboards-install-juju)=
### Install and set up Juju

The next step is to install Juju and initialize [LXD](https://canonical.com/lxd)
(a lightweight container hypervisor).

```shell
sudo snap install juju --classic --channel=3.5/stable
sudo snap install lxd
lxd init --auto
```

Files `/var/log/cloud-init.log` and `/var/log/cloud-init-output.log`
contain all low-level installation details.

Now that LXD and Juju are installed, the next step is to bootstrap Juju to use local LXD:

```shell
juju bootstrap localhost overlord
```

The controller can work with different models.
Most applications such as Opensearch or Opensearch Dashboards.
To set up a new "model" called tutorial, run:

```shell
juju add-model tutorial
```

You can now view the model you created above by entering the command `juju status`.
You should see something similar to the following output:

```text
Model     Controller  Cloud/Region         Version  SLA          Timestamp
tutorial  overlord    localhost/localhost  3.5.3    unsupported  14:22:02+02:00

Model "admin/tutorial" is empty.
```

(dashboards-graphical-interface)=
### Set up a graphical interface

There are graphical interfaces available for Multipass (see more details in the
[Multipass Graphical Interface chapter](https://multipass.run/docs/set-up-a-graphical-interface)).

We recommend to use RDP:

```shell
sudo apt install ubuntu-desktop xrdp remmina-plugin-rdp remmina
sudo passwd ubuntu # Set password here
```

Now you should be able to connect using the IP of the earlier Multipass list command:

```shell
remmina -c rdp://<IP>
```

If the environment comes up with a small resolution, use this great
[Stack Overflow suggestion](https://askubuntu.com/questions/914775/remmina-scale-resolution-when-connect-from-ubuntu-to-windows-10).

Note that after the graphical setup you may be instructed to restart the Multipass instance.
You probably want to do this before installing the services within
(as some may require re-initialization after a reboot otherwise).

(dashboards-deploy)=
## Get OpenSearch Dashboards up and running

The objective of Opensearch Dashboard is to display the contents of an Opensearch database.
This is why a  functional Opensearch database is a pre-requisite for the Dashboards application
to install successfully.

So, before going further, let's set up Charmed Opensearch.
Note that Opensearch has a mandatory requirement of TLS support, so we need to deploy it
alongside the `self-signed-certificates` charm and integrate (also known as "relate") them.

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

(dashboards-enable-tls)=
## Enable TLS encryption

Charmed Opensearch Dashboards supports HTTPS connections.
Configuration is similar to what we have seen for Opensearch – we just need
to integrate the Dashboards charm against the TLS charm:

```shell
juju integrate self-signed-certificates opensearch-dashboards
```

Once the two charms are successfully related, you should be able to access the same URL now using HTTPS.

(dashboards-access)=
## Access Opensearch Dashboards

Assuming that you have a virtual environment available
(as described in [Set up the environment](dashboards-setup-environment)),
open a browser and type there the following URL:

```text
http://<dashboards_juju_public_address>:5601
```

The address of the unit is available in the `juju status` output of the opensearch-dashboards unit.
For example, in the output from [Get OpenSearch Dashboards up and running](dashboards-deploy), this would be `10.163.9.173`.

You should see something like this:

![Openserach Dashboards - Multipass Desktop](img/multipass-desktop.jpeg)

(dashboards-setup-user)=
### Set up an Opensearch user

Set up a user using the `data-integrator` [charm](https://charmhub.io/data-integrator).

At deployment time the Opensearch index (in the example: `index_name`) has to be specified as well. This is an arbitrary, alphanumerical identifier of the users' data space in Opensearch.

User creation takes affect when integrated against the  `opensearch` charm.

```bash
juju deploy data-integrator --config index-name=<intex_name>
juju integrate data-integrator opensearch
```

```{note}
This user will have normal privileges -- meaning this user will only have access
to the index it owns. 
```

In case a broader access to the cluster's indices is needed,
it is possible to create an admin / privileged user as follows:

```bash
juju deploy data-integrator admin --config index-name=admin-index --config extra-user-roles="admin"
```

```{caution}
Please only create admin users when extremely needed, and handle with special care
as authenticating with an admin user grants full access to all indices in the cluster.
```

Retrieve user credentials running

```bash
juju run data-integrator/0 get-credentials
```

at the bottom of the output you should see something like:

```bash
password: 8kubD7nbWYZFHPVEzIVmTyqV42I7wHb4
<CA certificate here>
username: opensearch-client_15
```

(dashboards-index-pattern)=
### Create the "index pattern"

Log in to the Dashboard using these credentials.
Clicking the top left icon the main menu will pull down.
Select **Management** / **Dashboards Management** here

![Opensearch Dashboards - Initial view](img/initial-view.png)

Select **Index patterns** on the next view:

![Opensearch Dashboards - Index patterns](img/index-patterns.png)

Click on **create index pattern** at the bottom.

Adding the index name that used for `data-integrator` deployment (in our example: `testing`) as an index pattern enables Dashboard access to the user's Opensearch space.

![Opensearch Dashboards - Create index pattern](img/create-index-pattern.png)

Click on the **Next step** button, and finalize the index pattern creation.

As a verification, the user's index metadata will display.

(dashboards-visualize)=
### Add and visualize data

For test purposes, a simple method could do. Like generating data from the command-line, via the Opensearch API:

```text
for ID in `seq 1 100`
do 
    curl -sk -u opensearch-client_15:8kubD7nbWYZFHPVEzIVmTyqV42I7wHb4 \
    -XPUT https://10.4.151.211:9200/testing/_doc/${ID} \
    -H "Content-Type: application/json" \
    -d '{"test": "This is test ${ID}"}'
done
```

This is how raw data gets displayed in the Dashboard

![Opensearch Dashboards - Data](img/data.png)

(dashboards-data-visualization)=
### Data Visualization

Opensearch Dashboards offers a variety of diagrams and data displays.

Choose **Dashboards** in the main left-side menu, and you will be presented to the selection:

![Opensearch Dashboards - Visualization](img/visualization.png)

(dashboards-cleanup)=
## Clean up the environment

In case you may want to remove the Juju model, you should run:

```shell
juju remove-model tutorial --force --timeout 1s
```

If it's the whole Multipass instance that you would like to delete, you should execute this command:

```shell
multipass delete --purge my-vm
```

## What's next?

Congratulations! You have successfully deployed Charmed OpenSearch Dashboards,
configured TLS encryption, and explored data visualization capabilities.

To continue your journey with Charmed OpenSearch Dashboards:

* Explore the [How-to guides](dashboard-how-to-index) for guidance on practical tasks
* Review the [Reference documentation](dashboard-reference-index) for release notes
* Check out the [Charmed OpenSearch documentation](https://canonical-charmed-opensearch.readthedocs-hosted.com/) for backend integration options

<!-- ## Get involved

We'd love to hear from you:

* [Share your feedback](https://matrix.to/#/#charmhub-data-platform:ubuntu.com) - join our community chat
* [Report issues](https://github.com/canonical/opensearch-dashboards-operator/issues) or [Contribute to the project](https://github.com/canonical/opensearch-dashboards-operator) - help us make it better -->
