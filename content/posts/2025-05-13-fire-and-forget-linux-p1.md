+++
title = "No-ops Linux part 1: Automation, security and essentials"
date = "2025-05-13"
tags = ["cloud", "linux", "ops", "cdn", "duckdb", "caddy", "ansible"]
+++

In [Running containers on no-ops linux in 2025](/posts/2025-04-14-running-containers-on-the-cheap) I wrote about moving my hobby projects to a European cloud provider. I did an initial, manual setup in [Hetzner](https://www.hetzner.com/), which I've now automated. This weekend, I tested the setup. It takes me a few minutes now to get everything moved to a new host, and most of that has to do with DNS. I've got a reproducible setup, I can quickly provision up a machine locally or in any cloud that has Ubuntu 24.04. Reproducible infrastructure is ✨liberating✨

The goal is to document how to make a fire-and-forget Linux server that will mostly take care of its own ops, with an acceptable uptime and security level for my hobby projects. Once we're done, the server will:

- Update its packages, and reboot during nighttime, when required by updates.
- Run a [caddy](https://caddyserver.com/) proxy on the host system, ensuring everything's hosted on TLS with certificates issued from [letsencrypt](https://letsencrypt.org/).
- Run several persistent rootless containers using [podman](https://podman.io/), with a setup that brings them up on boot.
- Run a nightly job that updates some data and performs a rolling restart of some containers. The job runs in a container too. The data lives in S3-compatible object storage.
- Take care of automatically updating the containers.
- We'll also set up some monitoring so we can have 📨email notifications if the containers aren't working right. 

This covers a lot of ground, some of it is quite detailed. If you'd like to skip this incredibly long and technical read, you could go over and investigate the source code over at [github](https://github.com/kaaveland/fire-and-forget-linux) instead. It has been my goal to make something that other people can easily adapt to their own use. This description of how I made it might be a helpful guide to see which parts you should change or tinker with.

This post got so long that I broke it into three parts:

1. [This post](/posts/2025-05-13-fire-and-forget-linux-p1) covers local development of linux server configuration and essentials.
2. [The next post](/posts/2025-05-14-fire-and-forget-linux-p2) covers installation of [podman](https://podman.io/) and [caddy](https://caddyserver.com/). It concludes by deploying a very simple stateless webapp in a container.  
3. [The final post](/posts/2025-05-14-fire-and-forget-linux-p3) covers a more challenging deployment with jobs and rolling restarts, and discusses the strengths and weaknesses of this approach to hosting.

## Configuring Linux machines

For the longest time, I had hoped to do this with [cloud-init](https://cloudinit.readthedocs.io/en/latest/index.html). You can provide a user-data script when you order a machine with almost every cloud provider. When you get access to the machine, it's already configured (or very nearly done).

You shouldn't be putting secrets in user-data scripts. You can make user accounts, add public keys to them and install software and all sorts of useful things. I played with the idea of just setting up a new VM with cloud-init every time I needed a config change and just replacing the old one. I like that idea a lot. I still want to do it. But I really didn't find any good way of injecting the secrets that I require without manual intervention or reaching for a tool other than cloud-init.

For that reason I decided to settle for [Ansible](https://docs.ansible.com/ansible/latest/index.html) to configure the VMs, using `ansible-vault` to handle my secrets. There seemed little point in using cloud-init after that.

Both cloud-init and Ansible run counter to my goal of using as little YAML as possible, so that was deeply unsatisfying. But it works great! The last 8–12 years have given me a huge tolerance for YAML anyway. Surely, I'll survive? 😵

## Developing Ansible code

I had already decided to use Ubuntu 24.04 with unattended upgrades and unattended reboots. I wanted to develop locally, only ordering a server in a cloud when I was fairly confident I had a secure setup. The best way I know how to do that is to use [Vagrant](https://developer.hashicorp.com/vagrant). This tool can manage virtual machines locally, applying tons of different configuration management tools to configure them. Crucially, it supports ansible. After installing [VirtualBox](https://www.virtualbox.org/) I found a suitable [Vagrant box](https://portal.cloud.hashicorp.com/vagrant/discover) and ran:

```shell
vagrant init bento/ubuntu-24.04
```

This produces a Vagrantfile in the current directory. I edited mine to look like this:

```ruby
Vagrant.configure("2") do |config|
  config.vm.box = "bento/ubuntu-24.04"

  config.vm.provision "ansible" do |ansible|
    ansible.playbook = "initialize.yml"
  end
end
```

I put the following in `initialize.yml`, which is an ansible playbook:

```yaml
---
- name: Initialize Ubuntu host
  hosts: all
  become: true
  tasks:
    - name: Upgrade apt packages
      apt:
        update_cache: yes
        upgrade: yes
    - name: Ensure base packages
      apt:
        name:
          - vim
          - curl
          - git
          - unattended-upgrades
          - btop
          - iotop
          - nethogs
          - emacs-nox
          - strace
          - gnupg
          - lsb-release
          - systemd-container
          - nmap
          - fail2ban
          - ufw
        state:
          present
```

Here's a breakdown of the packages I put there:

- `unattended-upgrades` ensures that packages are upgraded without me doing anything on the machine. This represents a leap of faith that package upgrades won't break anything. We will be taking some precautions to make sure we discover breakage, later.
- `strace`, `nmap`, `nethogs`, `btop` and `iotop` are tools that I can use to investigate the state of affairs on the machine. When I `ssh` to a machine to debug it, I usually assume that I have these available. `curl` is also invaluable to check proxy configuration. 
- `vim`, `git`, `emacs-nox` are for interacting with source code or configuration on the machine. I don't anticipate using these, but I'd rather not have to install them manually later. I put both vim and emacs there because I was feeling a little impulsive and wild. No sane person would use `vim`, of course. 🤪 I do sometimes, but please don't tell any of my friends.
- `fail2ban` and `ufw` are security measures I want to use. `fail2ban` can be used to ban IPs that try to mess with the machine. Like bots that attempt to brute-force login to `ssh`. `ufw` is short for uncomplicated firewall, and that's what it is. It's a stateful firewall that's straightforward to use.
- We need `systemd-container` to obtain `machinectl`, which is useful for letting ansible control user-specific systemd settings without dealing with [D-Bus](https://en.wikipedia.org/wiki/D-Bus) ourselves.
- `lsb-release`and `gnupg` are useful if we want to add more apt sources, to install non-standard packages.

After this, we can bring up a virtual machine with:
```shell
vagrant up
```
It'll work for a while, then tell us the machine is configured. If we want to start over, we can use:

```shell
vagrant destroy -f; vagrant up
```

To reapply the playbook, we can use:
```shell
vagrant provision
```

To access an ssh-session, we can use:

```shell
vagrant ssh # logs in with the vagrant@ user, who has passwordless sudo
```

Now we have a nice and short feedback loop to iterate on the ansible configuration! No cloud required. Yet.

## Ansible best practices

There are some best practices we can choose to follow. Usually, that's a good idea. Since this is my hobby project, I will sometimes ignore some of them and undoubtedly regret it later. I simply haven't worked with Ansible for almost 10 years, so I'm probably very outdated.

But there's one best practice we'll try to follow closely: Keep the playbook lean, put most of the things into "roles." An ansible role is like a module. It can accept parameters and do many things. This gives us a way to assemble different playbooks out of different roles later, without doing so much work. So let's introduce some more structure:

```shell
mkdir -p roles/{caddy,base-install,app-user,podman}/{tasks,files,templates,handlers}
find roles
roles
roles/podman
roles/podman/tasks
roles/podman/files
roles/podman/templates
roles/podman/handlers
roles/base-install
roles/base-install/tasks
roles/base-install/files
roles/base-install/templates
roles/base-install/handlers
roles/app-user
roles/app-user/tasks
roles/app-user/files
roles/app-user/templates
roles/app-user/handlers
roles/caddy
roles/caddy/tasks
roles/caddy/files
roles/caddy/templates
roles/caddy/handlers
```

### Why would you make so many folders??

An ansible role is a directory that can consist of many parts. The most important ones are:

- `tasks/main.yml` defines (ideally idempotent) tasks that the role must run
- `templates` contain [jinja2](https://jinja.palletsprojects.com/en/stable/templates/) templates that can be used to render configuration in tasks
- `files` can contain stuff that we want the tasks to copy.
- `handlers/main.yml` defines some handlers that can react to tasks that have run; for example to reload some service if the configuration changed.

Let's build out the roles one at a time. First, we'll edit `initialize.yml` so that it contains only this:

```yaml
---
- name: Initialize Ubuntu host
  hosts: all
  become: true
  roles:
    - base-install
```

We're moving the base packages to the base-install role, in `roles/base-install/tasks/main.yml`:
```yaml
---
- name: Upgrade apt packages
  apt:
    update_cache: yes
    upgrade: yes
- name: Ensure base packages
  apt:
    name:
      - vim
      - curl
      - git
      - unattended-upgrades
      - btop
      - iotop
      - nethogs
      - emacs-nox
      - strace
      - gnupg
      - lsb-release
      - systemd-container
      - nmap
      - fail2ban
      - ufw
    state:
      present
```

We can use `vagrant provision` to check it. There shouldn't be any changes. 

### Securing `base-install`

I want the `base-install` role to take care of a few more things:

- Hardening `sshd`, so that it's more challenging to break into the machine that way
- Creating an `admin` user so that we can disable ssh-login for `root`
- Configuring `fail2ban` and `ufw`

These are things I'd like to set up on every machine, even if I end up with more machines eventually. Let's get to work. 

#### Handlers

First, we'll make some handlers that we're going to want to notify. We can put these into `roles/base-install/handlers/main.yml`:

```yaml
---
- name: Reload unattended-upgrades
  service:
    name: unattended-upgrades
    state: restarted
- name: Reload sshd
  service:
    name: ssh
    state: reloaded
- name: Reload systemd
  systemd:
    daemon_reload: yes
- name: Restart fail2ban
  ansible.builtin.service:
    name: fail2ban
    state: restarted
```

#### unattended-upgrades

We will want to add more tasks to `roles/base-install/tasks/main.yml`. Let's start small by setting the hostname, timezone and enabling unattended upgrades. Let's add these:

```yaml
- name: Set hostname to inventory hostname
  hostname:
    name: "{{ inventory_hostname }}"

- name: Set timezone to Europe/Oslo
  community.general.timezone:
    name: Europe/Oslo

- name: Enable unattended upgrades
  service:
    name: unattended-upgrades
    enabled: yes
  notify: Reload unattended upgrades

- name: Configure unattended-upgrades
  copy:
    dest: /etc/apt/apt.conf.d/99unattended-upgrades-custom
    content: |
      Unattended-Upgrade::Automatic-Reboot "true";
      Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
      Unattended-Upgrade::Automatic-Reboot-Time "02:00";
      Unattended-Upgrade::SyslogEnable "true";
  notify: Reload unattended upgrades
```

We'll use `vagrant provision` to test that this does the expected thing. At this point, we could let the machine run for a few days and verify that it reboots when there's a new security update, but we're not going to do that. There's still more work to do.

#### Securing `sshd`

Let's proceed to secure `sshd` a little more by adding new tasks to `roles/base-install/tasks/main.yml` again. I would like to block ssh-login with the `root` account, but before we can do that, we need to have an alternate account. `vagrant` has a dedicated `vagrant` user it can use, but we won't be so lucky when we're running ansible standalone against a cloud server, so we need to take care of this right away. Let's set it up:

```yaml
- name: Create admin
  user:
    name: admin
    state: present
    shell: /bin/bash
    createhome: yes
    groups: sudo
    append: yes

- name: Allow passwordless sudo for admin
  copy:
    dest: /etc/sudoers.d/admin
    content: "admin ALL=(ALL) NOPASSWD:ALL"
    mode: "0440"

- name: Configure authorized_keys for admin
  with_items: "{{ authorized_keys }}"
  authorized_key:
    user: admin
    key: "{{ item }}"
    state: present
```

Running `vagrant provision` now fails:

```shell
fatal: [default]: FAILED! => {"msg": "'authorized_keys' is undefined"}
```

That's because we didn't pass in any `authorized_keys` variable, but we use one in this role. Back to `initialize.yml` at the root:

```yaml
---
- name: Initialize Ubuntu host
  hosts: all
  become: true
  roles:
    - name: base-install
      vars:
        authorized_keys:
          - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE9K1p8B8FRCWJ0Ax4obDu+UsLzGgXDIdTYkCZ8FF54b
```

> 💡This changed the type of the list element in roles to an object, instead of a string. That's because we need to send it `vars` now.

This is how we can pass a variable into a role. This isn't the best place to put this key, but we'll find a better place later. `vagrant provision` now creates the `admin` user. You'll probably want to use a different public key unless you want me to have access to your vagrant box. We can check ssh access by running:

```shell
# 2222 is the default port vagrant uses to communicate with the box
ssh -p 2222 admin@localhost whoami
admin
```

Fantastic. It's time to configure ssh. Let's add this to `roles/base-install/tasks/main.yml`:

```yaml
- name: Require key for ssh-login
  copy:
    dest: /etc/ssh/sshd_config.d/harden.conf
    content: |
      PermitEmptyPasswords no
      LoginGraceTime 30s
      PasswordAuthentication no
      MaxAuthTries 3
      MaxSessions 3
      PermitRootLogin no
  notify: Reload sshd
```

We put this configuration into `/etc/ssh/sshd_config.d/harden.conf`, because the standard `sshd_config` automatically loads all snippets it finds in there. That way, we don't have to worry about package upgrades overwriting our configuration. This disables authenticating with passwords, and blocks attempts to log directly into the `root` account.

#### `fail2ban` and `ufw`

It's time to get `fail2ban` up! This package scans the server logs and blocks IPs that attempt to break in. This reduces the amount of noisy logs on the server, so it's a good idea to set it up even if you're not worried about breakin attempts actually succeeding.

Here's what we'll add to `roles/base-install/tasks/main.yml`:

```yaml
- name: Create Fail2Ban jail.local configuration
  copy:
    dest: /etc/fail2ban/jail.local
    content: |
      [DEFAULT]
      bantime = 1h
      # An IP is banned if it has generated "maxretry" during the last "findtime"
      findtime = 10m
      maxretry = 5

      [sshd]
      enabled = true
      port = ssh
      maxretry = 3
      bantime = 24h
    owner: root
    group: root
    mode: '0644'
  notify: Restart fail2ban

- name: Enable fail2ban
  service:
    name: fail2ban
    enabled: yes
```

Once again, we can run `vagrant provision` to verify that everything looks okay. This `fail2ban` config will block IPs that attempt to break into `sshd` for 24 hours. At this point, we can lock ourselves out of our server very easily if we use the wrong username or ssh-key. So let's not do that. 

Let's get uncomplicated firewall up with some sane defaults by adding even more YAML to `roles/base-install/tasks/main.yml`:

```yaml
- name: Set UFW default policies
  community.general.ufw:
    default: deny
    direction: incoming

- name: Set UFW default outgoing policy
  community.general.ufw:
    default: allow
    direction: outgoing

- name: Allow SSH on port 22/tcp (standard port)
  community.general.ufw:
    rule: allow
    port: '22'
    proto: tcp
    comment: 'Allow SSH access'

- name: Allow HTTP on port 80/tcp (standard port)
  community.general.ufw:
    rule: allow
    port: '80'
    proto: tcp
    comment: 'Allow HTTP access'

- name: Allow HTTPS on port 443/tcp (standard port)
  community.general.ufw:
    rule: allow
    port: '443'
    proto: tcp
    comment: 'Allow HTTPS access'

- name: Enable UFW
  community.general.ufw:
    state: enabled
```

This blocks all incoming ports other than `ssh`, `http` and `https`. Since `ufw` is a stateful firewall, it'll notice that we're using services like NTP and DNS and accept incoming packets from those when we want to use them, so it shouldn't interfere with anything.

### Wrapping up `base-install`

At this point I would feel comfortable deploying this onto a server in the cloud. It's very unlikely that anyone could succeed in breaking in, especially because there's almost no attack surface. We can't use this server for much other than reading manpages! In the [next part](/posts/2025-05-14-fire-and-forget-linux-p2), we'll make it a little more capable by setting up podman, a proxy and a simple container deployment.