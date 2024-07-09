# Set up the environment

In this section, you will set up your environment by:
* installing and setting up Multipass
* installing Juju and boostrapping LXD
* setting up a graphical interface with Multipass
---

## Install and set up Multipass


[Multipass](https://multipass.run/) is a quick and easy way to launch virtual machines running Ubuntu. It uses the “[cloud-init](https://cloud-init.io/)” standard to install and configure all the necessary parts automatically.

Installation of Multipass from [Snap](https://snapcraft.io/multipass) and launching a new VM using “[charm-dev](https://github.com/canonical/multipass-blueprints/blob/main/v1/charm-dev.yaml)” cloud-init config goes as:

```
sudo snap install multipass && \

multipass launch --cpus 4 --memory 8G --disk 30G --name my-vm charm-dev # tune CPU/RAM/HDD accordingly to your needs
```

(The full set of launch parameters is described[ here](https://multipass.run/docs/launch-command).)

Multipass [commands](https://multipass.run/docs/multipass-cli-commands) are generally short and intuitive. For example, to show all running VMs:

```
multipass list
```

When the new VM is up and running, connect using:

```
multipass shell my-vm
```

You can exit the Multipass VM using Ctrl + D or the exit command.

## Install and set up Juju

The next step is to install Juju and initialize [LXD](http://containers) (a lightweight container hypervisor).

```
sudo snap install juju --classic --channel=3.1/stable
sudo snap install lxd
lxd init --auto
```

(Files `/var/log/cloud-init.log and /var/log/cloud-init-output.log` contain all low-level installation details).

Now that LXD and Juju are installed, the next step is to bootstrap Juju to use local LXD:

```
juju bootstrap localhost overlord
```

The controller can work with different models. Most applications such as Opensearch or Opensearch Dashboards. To set up a new “model” called tutorial, run:

```
juju add-model tutorial
```

You can now view the model you created above by entering the command juju status. You should see something similar to the following output:
```
Model Controller Cloud/Region Version SLA Timestamp
tutorial overlord localhost/localhost 3.1.6 unsupported 23:20:53+01:00

Model "admin/tutorial" is empty.
```

## Set up a graphical interface

There are graphical interfaces available for multipass (see more details in the [Multipass Graphical Interface chapter](https://multipass.run/docs/set-up-a-graphical-interface)).

We recommend to use rdp:

```
sudo apt install ubuntu-desktop xrdp remmina-plugin-rdp remmina
sudo passwd ubuntu # Set password here
```

Now you should be able to connect using the IP of the earlier multipass list command:

```
remmina -c rdp://<IP>
```

If the environment comes up with a small resolution, use this great [Stackoverflow suggestion](https://askubuntu.com/questions/914775/remmina-scale-resolution-when-connect-from-ubuntu-to-windows-10).

Note that after the graphical setup you may be instructed to restart the multipass instance. You probably want to do this before installing the services within (as some may require re-initialization after a reboot otherwise).