+++
title = "No-ops linux part 2: Automating a self-updating container server"
date = "2025-05-13"
tags = ["cloud", "linux", "ops", "cdn", "duckdb", "caddy", "ansible"]
build = "render"
cascade = { _build = { list = "never", render = "always" } }
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

## Configuring Linux VMs

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

At this point I would feel comfortable deploying this onto a server in the cloud. It's very unlikely that anyone could succeed in breaking in, especially because there's almost no attack surface. We can't use this server for much other than reading manpages! Let's make it a little more capable.

## It's time to introduce ✨podman✨

`podman` is a tool for running containers. It's CLI-compatible with docker, and has deep and useful integrations with `systemd`, the `init` on most modern Linux installations. I want to use `systemd` to manage my containers for me with [podman systemd units](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html). This has nice features like auto-updating images, takes care of getting the log where I can read it, can restart failed containers and so on. `podman` will also run docker-compose files for you.

Ubuntu 24.04 (codename noble) ships with podman 4.9, which is a year old and missing some features I want:

- `systemd` template support for quadlet files (we'll get to this, don't worry)
- Some limited support for using k8s YAML with podman (I know I said I wanted to avoid YAML, but this may come in handy)
- Many quality of life improvements to quadlets

Ubuntu 25.04 (codename plucky) has podman 5.4, which has everything I want, but 25.04 isn't Long Term Support and not available at all cloud providers.

It's a little dirty, but what I'll do is to add the podman package from 25.04. This is not without risk, it could break things in the future.

We'll add the 25.04 sources to apt, using the new-fangled and cool `.sources` format. I need to use a template for this because my laptop is running on arm, but I'm probably going to end up provisioning to an x86 machine, and there are different package URIs for those. Let's create `roles/podman/templates/plucky.sources.j2` with this content:

```
Types: deb
{% if ansible_architecture == 'aarch64' or ansible_architecture == 'arm64' %}
URIs: http://ports.ubuntu.com/ubuntu-ports
{% else %}
URIs: http://archive.ubuntu.com/ubuntu
{% endif %}
Suites: plucky plucky-updates
Components: main universe restricted
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
```

The `{% if ... }` is jinja2-syntax, and ansible knows what kind of architecture the machine has. But just adding this, we risk upgrading tons of packages to the 25.04 distribution, and we don't want that. We can limit the blast radius by setting up a `.pref` file that pins only the packages we think we need to 25.04. I found a list at [this issue](https://github.com/containers/podman/discussions/25582) that looks good. We'll add this to `roles/podman/tasks/main.yml` which should hopefully fix it:

```yaml
---
- name: Prefer plucky for podman
  copy:
    dest: /etc/apt/preferences.d/podman-plucky.pref
    content: |
      Package: podman buildah golang-github-containers-common crun libgpgme11t64 libgpg-error0 golang-github-containers-image catatonit conmon containers-storage
      Pin: release n=plucky
      Pin-Priority: 991

      Package: libsubid4 netavark passt aardvark-dns containernetworking-plugins libslirp0 slirp4netns
      Pin: release n=plucky
      Pin-Priority: 991

      Package: *
      Pin: release n=plucky
      Pin-Priority: 400

- name: Add plucky as a source
  template:
    dest: /etc/apt/sources.list.d/plucky.sources
    src: plucky.sources.j2

- name: Install podman
  apt:
    update_cache: true
    name:
      - podman
    state: present
```

Next, we'll need to add this to the roles list in `initialize.yml`. It should now look like this:

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
    - podman
```

Let's test it with `vagrant provision`, then check:

```shell
vagrant ssh -- podman --version
podman version 5.4.1
```

Fantastic. This role was much less work than the previous one!

## We need to talk about [caddy](https://caddyserver.com/)

I need my server to respond to HTTP and HTTPS, so we need something listening on port 80 and 443 to route http traffic to applications running in containers. I've had lots of experience using nginx and HAProxy, which are both excellent products. But I want this setup to be easily reproducible, fire-and-forget, and I haven't found a great way to automate letsencrypt TLS certificates with these proxies. I _have_ done it before, I just want something that's more friendly to me.

Caddy promises to do all the heavy lifting with almost no setup and seems to have modern defaults, with very little configuration required in general. I like that a lot, so I want to give it a go. A proxy is a part of the stack that we can easily replace later if we want. I hear [traefik integrates with podman and letsencrypt](https://gerov.eu/posts/traefik-for-podman/) too.

We could choose to run caddy in a container to make the host operating system even leaner. For now, I want to let unattended-upgrades deal with patching it. So we'll set it up with `apt`. This probably gives us older, more stable, releases with fewer features. I think it should be easy to change our minds later if we discover something really cool in a release we don't have.

There are many ways to configure caddy, but it looks like using `/etc/caddy/Caddyfile` will be the quickest way to get started with the `apt` package. I'm going to need to proxy to several backends, and I don't want to centralize the configuration to this file, but thankfully it has an `import` directive. So this configuration here should do what I want:

```
{
	email robin@example.com
	servers {
		timeouts {
			read_body 5s
			read_header 5s
			write 5s
			idle 3m
		}
	}
}

import /etc/caddy/proxies.d/*
```

If you want to use this, please enter your actual email, or letsencrypt won't be able to reach you. Also check if you want to adjust those timeouts, these are global. We set `read_body` and `read_header` timeouts to low-ish values to make it a bit harder for mean clients to drain all our sockets. We'll put the configuration in `roles/caddy/files/Caddyfile`. 

Next up, we need some more ✨tasks✨ in `roles/caddy/tasks/main.yml`:
```yaml
---
- name: Install caddy
  apt:
    state: present
    update_cache: true
    name: caddy

- name: Ensure proxies.d
  file:
    dest: /etc/caddy/proxies.d/
    state: directory

- name: Set up global caddyfile
  copy:
    dest: /etc/caddy/Caddyfile
    src: Caddyfile
  notify: reload caddy

- name: Enable caddy
  systemd:
    name: caddy
    enabled: yes
```

You may have noticed that there's a `notify: reload caddy` instruction here, so we'll also need a handler in `roles/caddy/handlers/main.yml`:

```yaml
---
- name: reload caddy
  systemd:
    name: caddy
    state: reloaded
```

Let's keep expanding our `initialize.yml` playbook and add the caddy role:

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
    - name: podman
    - name: caddy
```

`vagrant provision` is happy, so I am happy too. Later when we set up applications, we'll make them write their proxy configuration to `/etc/caddy/proxies.d/appname`, so we'll revisit caddy once we've got an application running.

## Behold, an empty server that could run something

We have all the pieces we need to run some sort of application now:

- orchestration with `systemd`
- containerization with `podman`
- loadbalancing and http routing with `caddy`

We did all this work, and all we have to show for it is that we've got a server listening on port 80 and 443, telling us nothing is found anywhere. That won't do at all.

Currently, I need to run two applications on here:

- [eugene-web](https://kaveland.no/eugene/web.html), source code available [here](https://github.com/kaaveland/eugene/tree/main). This is written in Rust and checks postgres SQL migrations for issues on a simple API.
- [kollektivkart](https://kollektivkart.arktekk.no/), source code available [here](https://github.com/kaaveland/bus-eta). This is written in Python and DuckDB, and visualizes where delays in norwegian public transit occur. This is backend has a "data pond"; it relies on around ~40GB of data in an S3 bucket and runs jobs to keep it updated.

It makes the most sense to start deploying `eugene-web`, since it is a very basic stateless backend. 

I want to isolate these services from one another at the linux-user level, so we'll need a user that can have `systemd` units. Since I foresee this being required for both the apps, we'll fill in the `app-user` role now.

## To be an app-user or not to be

Since we do not want to install our applications with systemd on the root level, we have to jump through some hoops here. In particular, we need to enable _linger_ for the users, so their systemd units can come up on reboots. Otherwise, the user must be logged in to have their units running. We also need to create the actual users, and we'll want to set up some authorized keys for them.

> 💡Linger is critical for this setup to work. The [Arch Linux wiki](https://wiki.archlinux.org/title/Systemd/User) has a technical explanation, look under section 2.2 Automatic start-up of systemd user instances. 

We'll also create the folders for where the systemd units and the quadlet definitions go. In total, we get this nice and cute `roles/app-user/tasks/main.yml`, but we'll probably find a reason to revisit and make it terrible later on:

```yaml
---
- name: "Create {{ user }}"
  user:
    name: "{{ user }}"
    state: present
    shell: /bin/bash
    createhome: yes

- name: "Enable linger for {{ user }}"
  command: loginctl enable-linger {{ user }}
  
- name: "Configure authorized keys for {{ user }}"
  with_items: "{{ authorized_keys }}"
  authorized_key:
    user: "{{ user }}"
    key: "{{ item }}"
    state: present

- name: "Create quadlet home for {{ user }}"
  file:
    path: "/home/{{ user }}/.config/containers/systemd"
    state: directory
    mode: "0700"
    owner: "{{ user }}"
    group: "{{ user }}"

- name: "Create systemd units home for {{ user }}"
  file:
    path: "/home/{{ user }}/.config/systemd/user"
    state: directory
    mode: "0700"
    owner: "{{ user }}"
    group: "{{ user }}"


- name: "Create systemd wants home for {{ user }}"
  file:
    path: "/home/{{ user }}/.config/systemd/user/default.target.wants"
    state: directory
    mode: "0700"
    group: "{{ user }}"
    owner: "{{ user }}"
```

These definitions will be shared between the kollektivkart and the eugene backends, but we're not adding them to `initialize.yml`. Instead, we'll use the `dependencies:` key in `roles/eugene/meta/main.yml` to ensure that it _includes_ an `app-user` role with a concrete variable for `user`.

## Careful With That Lock, Eugene

Let's start by making the directory tree we'll need:

```shell
mkdir -p roles/eugene/{tasks,meta,defaults,templates,files}
```

Did you notice that we introduced two new subfolders in the role all at once? With no warning up front? Don't worry, we'll put something in those right away so we can discuss what they are for.

In `roles/eugene/defaults/main.yml`, we'll put this snippet:

```yaml
user: eugene
```

This defines a value for the `user` parameter required by the `app-user` role, _and_ allows whoever calls us to override it. Aren't we being nice to our future selves? 🙌

In `roles/eugene/meta/main.yml`, we'll put this:

```yaml
dependencies:
  - role: app-user
```

This says that in order for the `eugene` role to work, it depends on the `app-user` role with the same `user` variable to exist. It means that when people ask for `eugene`, they also get `app-user`. They don't have to worry about remembering it. 

I'll put this into `roles/app-user/meta/main.yml` too:

```yaml
allow_duplicates: yes
```

Otherwise, when we make the next application role and make it depend on `app-user`, it'll think `app-user` has already done its thing, even if the `{{ user }}` variable is different.

_Now_ we can try to modify `initialize.yml`:

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
    - name: podman
    - name: caddy
    - name: eugene
```

Oh no, `vagrant provision` tells us we forgot about the authorized keys:

```yaml
TASK [app-user : Configure authorized keys for eugene] *************************
fatal: [default]: FAILED! => {"msg": "'authorized_keys' is undefined"}
```

We don't want to duplicate those, so we no longer want to set them directly on the `base-install` role. For now, we'll stick to inlining it into the playbook and think about this issue later:

```yaml
---
- name: Initialize Ubuntu host
  hosts: all
  become: true
  vars:
    authorized_keys:
      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE9K1p8B8FRCWJ0Ax4obDu+UsLzGgXDIdTYkCZ8FF54b
  roles:
    - name: base-install
    - name: podman
    - name: caddy
    - name: eugene
```

> 💡We could change all the `roles` from objects back into strings now, but I would like to explicitly pass `vars:` to them at some point, so _I_ won't. 

Notice how we just rudely moved it up two levels, and it became a global variable that all the roles can use. I really prefer passing variables like this explicitly to the roles. I think I'll still be able to sleep at night, though, since this is a basic setup for only myself.

Note that this means that the same set of keys will be used for both `admin` and the `app-user` roles. Probably not what we'd want if we were doing anything important! But now, `vagrant provision` is happy again, and it's time to make the `eugene`-specific tasks.

### What is this mythical quadlet anyway?

_Finally_ getting to the fun part. By my count, that took around 260 lines of YAML. Feel free to take a break, you've deserved it!

> 💡I don't have a better way of explaining what a quadlet is than stating that it's a nice systemd-wrapping around podman concepts like containers and networks. Previously, there used to be a way to use a [generator](https://docs.podman.io/en/latest/markdown/podman-generate-systemd.1.html) to make systemd units out of podman definitions. It's still there. It is handy to know about when things don't work like expected. It will often tell you why your quadlets aren't working. It will either tell you about errors or generate systemd units corresponding to your quadlets. To check all the quadlets in `~/.config/containers/systemd`:

```shell
/usr/lib/systemd/system-generators/podman-system-generator --user --dryrun
```


We'll make a `eugene.container` quadlet now. Let's put it in `roles/eugene/files/eugene.container`:

```toml
[Unit]
Description=Eugene API for SQL migration validation
After=network.target

[Container]
Image=ghcr.io/kaaveland/eugene-web:latest
PublishPort=127.0.0.1:3000:3000
StopSignal=SIGKILL
AutoUpdate=registry

[Service]
SyslogIdentifier=eugene-web
CPUQuota=100%
MemoryMax=128M

[Install]
WantedBy=default.target
```

Here we're describing what we're running, then specifying in the `[Container]` section what image to run, and where to publish the port. We're publishing it to the loopback address on `127.0.0.1`, on port 3000 where caddy can find it. We're also telling podman how to kill the container nicely, and that we should auto-update it from the registry.

> 💡This `[Container]` uses just a _tiny_ subset of what we can set on it. Check the [documentation](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html#container-units-container) to discover more fun settings! You can discover more `[Service]` settings [here](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html).

I feel like the networking here is suboptimal, but I'll work on that some other time.

In the `[Service]` section, we set some limits for how many resources it can use. We'll allow `eugene` to use one whole CPU core and 128MB RAM, which is significantly more than what it really needs.

In the `[Install]` section, we're telling `systemd` that we want this thing to run on boot. Next, we're going to need a caddy configuration. Let's put that in `roles/eugene/templates/eugene.caddy.j2`:

```
api{{ env_suffix }}.kaveland.no {
    encode
    handle /eugene/app/* {
        reverse_proxy localhost:3000
    }
    log
}
```

There's a potential problem that will require us to refactor later here. If we want to publish other apis to this hostname, we probably need to modify this file, which currently belongs to the `eugene` role. We'll accept this technical debt and move on with our lives for now. I decided to introduce an `env_suffix` variable here so that I can make environments if I ever feel like it's too exciting to have only a single deployment. If `env_suffix` isn't defined, we'll get an error, so we'll need to pass it to this module. It seems... prudent for me to set up a machine on `api-test.kaveland.no` to check that everything works _before_ I take over `api.kaveland.no`, so let's pass it from `initialize.yml`:

```yaml
---
- name: Initialize Ubuntu host
  hosts: all
  become: true
  vars:
    authorized_keys:
      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE9K1p8B8FRCWJ0Ax4obDu+UsLzGgXDIdTYkCZ8FF54b
  roles:
    - name: base-install
    - name: podman
    - name: caddy
    - name: eugene
      vars:
        env_suffix: -test 
```

Let's tie it together in `roles/eugene/tasks/main.yml`:

```yaml
---
- name: Set up eugene quadlet unit
  copy:
    dest: "/home/{{ user }}/.config/containers/systemd/eugene.container"
    owner: "{{ user }}"
    group: "{{ user }}"
    mode: "0600"
    src: eugene.container

- name: Reload systemd
  command: machinectl shell {{ user }}@ /bin/systemctl --user daemon-reload

- name: Enable eugene
  command: machinectl shell {{ user }}@ /bin/systemctl --user enable eugene

- name: Start eugene
  command: machinectl shell {{ user }}@ /bin/systemctl --user start eugene

- name: Configure reverse proxy
  template:
    dest: "/etc/caddy/proxies.d/eugene.caddy"
    src: eugene.caddy
    owner: root
    group: root
    mode: "0644"
  notify: reload caddy
```

Here we're using `machinectl` to do systemd shenanigans because of DBus issues if we try to use `become_user: "{{ user }}"` with ansible. Ideally, we would like to run these commands with the ansible modules, but this is good enough for me. In here, we issue `systemctl --user daemon-reload` to make `systemd` discover our quadlet, then we enable and start it. Let's check if it's running:

```shell
ssh -p2222 eugene@localhost systemctl --user status eugene
× eugene.service - Eugene API for SQL migration validation
     Loaded: loaded (/home/eugene/.config/containers/systemd/eugene.container; generated)
     Active: failed (Result: exit-code) since Tue 2025-05-13 22:45:34 CEST; 3min 13s ago
   Duration: 57ms
    Process: 79280 ExecStart=/usr/bin/podman run --name systemd-eugene --cidfile=/run/user/1002/eugene.cid --replace --rm --cgroups=split --stop-signal SIGKILL --sdnotify=conmon -d --label io.containers.autoupdate=registry --publish 127.0.0.1:3000:3000  ghcr.io/kaaveland/eugene-web:latest (code=exited, status=1/FAILURE)
    Process: 79303 ExecStopPost=/usr/bin/podman rm -v -f -i --cidfile=/run/user/1002/eugene.cid (code=exited, status=0/SUCCESS)
   Main PID: 79280 (code=exited, status=1/FAILURE)
        CPU: 117ms
```

Bummer. The developer (me) hasn't built the eugene-web image with arm64-support (although eugene-cli has both arm64, x86 and even a .exe). That was dumb of me. But otherwise, this is working as intended:

```shell
 ssh -p2222 admin@localhost sudo reboot 0
 ssh -p2222 admin@localhost whoami
 admin
 ssh -p2222 eugene@localhost systemctl --user status eugene
× eugene.service - Eugene API for SQL migration validation
     Loaded: loaded (/home/eugene/.config/containers/systemd/eugene.container; generated)
     Active: failed (Result: exit-code) since Tue 2025-05-13 22:51:09 CEST; 6s ago
   Duration: 62ms
    Process: 1848 ExecStart=/usr/bin/podman run --name systemd-eugene --cidfile=/run/user/1002/eugene.cid --replace --rm --cgroups=split --stop-signal SIGKILL --sdnotify=conmon -d --label io.containers.autoupdate=registry --publish 127.0.0.1:3000:3000 ghcr.io/kaaveland/eugene-web:latest (code=exited, status=1/FAILURE)
    Process: 1949 ExecStopPost=/usr/bin/podman rm -v -f -i --cidfile=/run/user/1002/eugene.cid (code=exited, status=0/SUCCESS)
   Main PID: 1848 (code=exited, status=1/FAILURE)
        CPU: 209ms
```

So, once we get this on an x86 machine, it'll be fire-and-forget, with podman taking good care of eugene. Perfect!

`eugene-web` is almost the best-case for something we'll host. It starts in milliseconds and can handle a few hundred requests a second on a single CPU core. Let's take a look at something that is a little gnarlier to host.

## The kollektivkart data pond

[kollektivkart](https://kollektivkart.arktekk.no) pulls data from Google BigQuery to S3-compatible storage, runs some [DuckDB](https://duckdb.org) queries on it and shows it in a map (somewhat simplified). The data set it pulls from is open data, and documented at [data.entur.no](https://data.entur.no).

The service _could easily_ use a local disk. It pulls down around 20GB of data from BigQuery as partitioned parquet datasets. After crunching everything I find interesting, it occupies around 40GB of space. This will work fine on even a cheap cloud virtual machine. But it is incredibly nice to make the server stateless, to the degree that I can. This ensures that I can quickly and easily replace the machine with another one. So, that's what I'll do.


### Keep it secret, keep it safe

For this setup to work, I need some secret values that I won't share with anyone. Remember when I decided to go for ansible instead of cloud-init? This is what I attempted to foreshadow. Notably, I need:

- BigQuery credentials
- S3 credentials

I'm not interested in anyone in the entire world ever getting access to these, other than me. This is what I wanted to use `ansible-vault` for. So let's initialize a secrets file with ansible-vault:

```shell
ansible-vault create secrets.yml
New Vault password:
Confirm New Vault password:
```

After confirming my password, it opens my `$EDITOR` (meaning emacs, naturally) and I can enter secrets. I chose the password "hugabuga" for this one, and I will populate it with the wrong secret values but the right keys, so you can play with it if you want. You should make a much better password. This one is taken!

The contents should look like this:

```yaml
aws_access_key_id: "Did you really think"
aws_secret_access_key: "I would put real credentials in here"
bq_service_account: "And share the password?"
```

Once I save the file and close it, ansible-vault encrypts it, and it looks like this:
```
$ANSIBLE_VAULT;1.1;AES256
30313539343136313831616265626561646563323064313538346666623032646136666338613137
3536366234316664373331326463613965343132306339370a313539346231656131373637303931
61616630653635343231333138383763316661326233626535666430643930383565346436646662
3737626532656538370a333263343132323832636362633064633536336133363464346363633637
35326439356664326666383963636535313132323536376266623434646631316533653731326461
30643838323265643063343039616537373632663165646463636330626234363766383635656531
35623763643963316362313662663032333961303230333165363232363064626332363335663461
62633634303937623036393562333561666231346366616363323735653531313836333536376362
37326132306535386664616661326131303433316130343136396437653563323264313031323263
63613462333661646235396664306661643839653363343938393034626439316565653530393036
66313063373335316535613131386530616538323036343932633565653138303737383334336431
66396335313534316232
```

AES256 is pretty strong, so in theory I can share the real file with people I don't trust. But there's no real reason for me to do that, so out of an abundance of caution, I won't.

This presents a new challenge, though. `vagrant` won't know how to open this, so now we need to learn how to invoke ansible ourselves. Sigh.

### The inventory file

Since Ansible can provision many hosts all at once, it has a concept of an inventory file. We'll create a simple one that works with our vagrant setup. Let's put this in `hosts.ini`:

```ini
[vagrant]
127.0.0.1
[vagrant:vars]
ansible_ssh_user=admin
ansible_become_user=root
ansible_ssh_port=2222
```

Now we can apply our ansible playbook to the vagrant _host group_ using this command:

```shell
# --ask-vaultpass gives you a prompt
# we could also use --vault-password-file if we were too lazy to type hugabuga 
ansible-playbook -i hosts.ini --limit vagrant --ask-vault-pass initialize.yml 
```

Eventually we'll probably want to add a `[prod]` section and a `[prod:vars]` section.

### Writing the kollektivkart role

This new role is going to look a little bit like the eugene role, so let's create the same directory tree for it:

```shell
mkdir -p roles/kollektivkart/{tasks,meta,defaults,templates,files}
```

Let's also reuse the same `env_suffix` variable from `eugene`, and modify `initialize.yml`:

```yaml
---
- name: Initialize Ubuntu host
  hosts: all
  become: true
  vars:
    authorized_keys:
      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE9K1p8B8FRCWJ0Ax4obDu+UsLzGgXDIdTYkCZ8FF54b
  vars_files:
    - secrets.yml
  roles:
    - name: base-install
    - name: podman
    - name: caddy
    - name: eugene
      vars:
        env_suffix: -test
    - name: kollektivkart
      vars:
        env_suffix: -test
```

Notice how we added `vars_files`! This is the crucial part that makes ansible and ansible-vault work together, otherwise they'd just wander off in different directions, and we would be very confused and have no secrets. 

We can reuse the exact same `meta/main.yml` file:

```shell
cp roles/{eugene,kollektivkart}/meta/main.yml
```

But we will want a different default username, so let's put this in `roles/kollektivkart/defaults/main.yml`:

```yaml
user: kollektivkart
```

Next, I'll place the bq credentials in the home folder belonging to the kollektivkart user and verify that everything seems to work. This next part goes in `roles/kollektivkart/tasks/main.yml`:

```yaml
---
- name: Set up bq credentials
  copy:
    dest: "/home/{{ user }}/bq_credentials"
    mode: "0600"
    owner: "{{ user }}"
    group: "{{ user }}"
    content: "{{ bq_service_account }}"
```

We run the long-winded ansible-command again and check that it did what we wanted:

```shell
ssh -p2222 kollektivkart@localhost cat bq_credentials
And share the password?
```

Right, we can use secrets now. The kollektivkart webapp requires some additional configuration. It uses a bunch of environment variables, so we'll put them in an environment file that podman can use. Since this contains secrets, we'll use a template. Let's create `roles/kollektivkart/templates/kollektivkart.conf.j2`:

```shell
SIMPLE_ANALYTICS=true
AWS_REGION=hel1.your-objectstorage.com
DUCKDB_S3_ENDPOINT=hel1.your-objectstorage.com
AWS_ACCESS_KEY_ID={{ aws_access_key_id }}
AWS_SECRET_ACCESS_KEY={{ aws_secret_access_key }}
PARQUET_LOCATION=s3://kaaveland-private-bus-eta
```

We'll need to add a task to `roles/kollektivkart/tasks/main.yml` to render the template:

```yaml
- name: Set up kollektivkart.conf
  template:
    dest: "/home/{{ user }}/kollektivkart.conf"
    src: kollektivkart.conf.j2
    mode: "0600"
    owner: "{{ user }}"
    group: "{{ user }}"
```

We should probably find a way to use [podman secrets](https://docs.podman.io/en/latest/markdown/podman-secret-create.1.html) for this eventually, but for now, an env file will do.

#### Quadlet templates and automatically starting up on boot

When kollektivkart starts up, it reads a lot of data from S3 into memory. This takes a fairly long time, it's nothing like `eugene-web` at all. It also takes a long time to respond to requests. There's no way we can restart this thing without disappearing from the internet for a while. Or is there?

Actually, we could run two containers and restart them one at a time. There's probably a way to make caddy discover when one is down. With our current network setup, that means we'll want to start the same exact setup on two different http ports.

`systemd` makes this really easy. Let's add a task to write the quadlet:
```yaml
- name: Set up kollektivkart quadlet
  copy:
    dest: "/home/{{ user }}/.config/containers/systemd/kollektivkart@.container"
    owner: "{{ user }}"
    group: "{{ user }}"
    mode: "0600"
    content: |
      [Unit]
      Description=Kollektivkart API container on port %i
      After=network.target

      [Container]
      Image=ghcr.io/kaaveland/bus-eta:latest
      PublishPort=127.0.0.1:%i:8000
      Entrypoint=/app/.venv/bin/gunicorn
      Exec=kollektivkart.webapp:server --preload --bind 0.0.0.0:8000 --chdir=/app --workers=3
      AutoUpdate=registry
      EnvironmentFile=/home/{{ user }}/kollektivkart.conf

      [Service]
      SyslogIdentifier=kollektivkart
      Restart=on-failure
      CPUQuota=200%
      MemoryMax=3G
```

There are two strange new things introduced here:

1. The quadlet name is `kollektivkart@.container`. This makes the file a quadlet template instead of a regular quadlet.
2. We publish the port to `127.0.0.1:%i`. The `%i` is where we receive the template parameter.

We'll provision this with the long-winded ansible command, then play around in the shell a little bit:

```shell
ssh -p 2222 kollektivkart@localhost
kollektivkart@127:~$ systemctl --user daemon-reload
kollektivkart@127:~$ systemctl --user start kollektivkart@8000
kollektivkart@127:~$ systemctl --user start kollektivkart@8001
kollektivkart@127:~$ systemctl --user status
● 127.0.0.1
    State: running
    Units: 152 loaded (incl. loaded aliases)
     Jobs: 0 queued
   Failed: 0 units
    Since: Tue 2025-05-13 22:49:06 CEST; 1h 1min ago
  systemd: 255.4-1ubuntu8.6
   CGroup: /user.slice/user-1003.slice/user@1003.service
           ├─app.slice
           │ └─app-kollektivkart.slice
           │   ├─kollektivkart@8000.service
           │   │ ├─libpod-payload-fdd0fbf5a81144fdfc6d8383debbd0808cd4a569dadba51e9273280bec5bab8b
           │   │ │ └─57618 /app/.venv/bin/python /app/.venv/bin/gunicorn kollektivkart.webapp:server --preload --bind 0.0.0.0:8000 --chdir=/app --workers=3
           │   │ └─runtime
           │   │   ├─57612 /usr/bin/pasta --config-net -t 127.0.0.1/8000-8000:8000-8000 --dns-forward 169.254.1.1 -u none -T none -U none --no-map-gw --quiet --netns /run/user/1003/netns/netns-816a4334-4656-6ff0-3>
           │   │   └─57616 /usr/bin/conmon --api-version 1 -c fdd0fbf5a81144fdfc6d8383debbd0808cd4a569dadba51e9273280bec5bab8b -u fdd0fbf5a81144fdfc6d8383debbd0808cd4a569dadba51e9273280bec5bab8b -r /usr/bin/crun ->
           │   └─kollektivkart@8001.service
           │     ├─libpod-payload-67e2568560852fe2f5c1ed0d41893dfd7b58b3ee8c5f8e9fba3956460aa476c4
           │     │ └─57655 /app/.venv/bin/python /app/.venv/bin/gunicorn kollektivkart.webapp:server --preload --bind 0.0.0.0:8000 --chdir=/app --workers=3
           │     └─runtime
           │       ├─57650 /usr/bin/pasta --config-net -t 127.0.0.1/8001-8001:8000-8000 --dns-forward 169.254.1.1 -u none -T none -U none --no-map-gw --quiet --netns /run/user/1003/netns/netns-af5d94e5-41fc-cc37-3>
           │       └─57653 /usr/bin/conmon --api-version 1 -c 67e2568560852fe2f5c1ed0d41893dfd7b58b3ee8c5f8e9fba3956460aa476c4 -u 67e2568560852fe2f5c1ed0d41893dfd7b58b3ee8c5f8e9fba3956460aa476c4 -r /usr/bin/crun ->
```

This is a very long-winded way of saying that we can very easily start this container in many replicas now, each on different ports. It's stuck in a reboot-loop, though:

```shell
kollektivkart@127:~$ journalctl --user | grep restart | tail -n1
May 13 16:53:42 127.0.0.1 systemd[39527]: kollektivkart@8000.service: Scheduled restart job, restart counter is at 42.
kollektivkart@127:~$ systemctl --user stop kollektivkart@8000
kollektivkart@127:~$ systemctl --user stop kollektivkart@8001
```

That's because we aren't using the right S3 access key for some reason. I can easily fix that, but you can't! There are literally secrets between us.

One thing that you cannot do with a quadlet template is to `systemctl enable` it. So how do we make sure it comes up on boot? The best way I've found is to make a regular systemd unit that boots the template. We can add this to `roles/kollektivkart/tasks/main.yml`:

```yaml
- name: Set up kollektivkart start on boot
  copy:
    dest: "/home/{{ user }}/.config/systemd/user/kollektivkart-starter.service"
    owner: "{{ user }}"
    group: "{{ user }}"
    mode: "0600"
    content: |
      [Unit]
      Description=Start Kollektivkart Application Instances (8000 and 8001)
      After=network.target
      [Service]
      Type=oneshot
      RemainAfterExit=yes
      ExecStart=/usr/bin/systemctl --user start kollektivkart@8000
      ExecStart=/usr/bin/systemctl --user start kollektivkart@8001
      [Install]
      WantedBy=default.target
```

Now we can do our `machinectl` shenanigans by adding these tasks to `roles/kollektivkart/tasks/main.yml`:

```yaml
- name: Reload systemd
  command: machinectl shell {{ user }}@ /bin/systemctl --user daemon-reload

- name: Enable kollektivkart
  command: machinectl shell {{ user }}@ /bin/systemctl --user enable kollektivkart-starter
```

After running `ansible-playbook` one more time, let's try booting the machine:

```shell
ssh -p2222 admin@localhost sudo reboot 0
ssh -p2222 kollektivkart@localhost systemctl --user status
● 127.0.0.1
    State: running
    Units: 153 loaded (incl. loaded aliases)
     Jobs: 0 queued
   Failed: 0 units
    Since: Tue 2025-05-13 23:21:22 CEST; 3s ago
  systemd: 255.4-1ubuntu8.6
   CGroup: /user.slice/user-1003.slice/user@1003.service
           ├─app.slice
           │ └─app-kollektivkart.slice
           │   ├─kollektivkart@8000.service
           │   │ ├─libpod-payload-bb7340e633ea971aa8c57123e2909e40c744d2371ff70a8d2bba4a682244baa9
           │   │ │ └─1871 /app/.venv/bin/python /app/.venv/bin/gunicorn kollektivkart.webapp:server --preload --bind 0.0.0.0:8000 --chdir=/app --workers=3
...
```

Success! But so far, nobody can reach this service without using `ssh`. We'll need to configure caddy to proxy to these two instances. 

#### Proxy configuration

Let's make a template for the configuration in `roles/kollektivkart/templates/kollektivkart.caddy.j2`:

```
kollektivkart{{ env_suffix }}.kaveland.no {
    encode
    reverse_proxy {
       to localhost:8000 localhost:8001
       health_uri /ready
       health_interval 2s
       health_timeout 1s
       health_status 200
    }
    log
}
```

We're setting up caddy to proxy for both instances, relying on it to discover on the `/ready` HTTP-endpoint when the backend can receive traffic. We'll let it check every two seconds. If we take down a container, caddy should stop sending requests to it within a couple of seconds. This is a good enough quality of service for my hobby projects. We need to add rendering of the template to `roles/kollektivkart/tasks/main.yml`:

```yaml
- name: Configure reverse proxy
  template:
    dest: "/etc/caddy/proxies.d/kollektivkart.caddy"
    src: kollektivkart.caddy.j2
    owner: root
    mode: "0644"
  notify: reload caddy
```

#### But what about my job?

The same image contains a job that needs to run once per night to ingest new public transit data from [data.entur.no](https://data.entur.no). Once it's crunched the latest data, we need to restart the kollektivkart service. We already decided that losing requests for ~2 seconds at a time is fine. We'll put a small rolling-restart script on the server. Let's start by putting this file in `roles/kollektivkart/files/rolling-restart`:

```shell
#!/usr/bin/env bash

set -euf -o pipefail

echo "Perform rolling-restart of kollektivkart@8000 and kollektivkart@8001"

for port in 8000 8001; do
  systemctl --user restart kollektivkart@$port
  for attempt in $(seq 1 20); do
    sleep 3;
    if curl -s -o /dev/null -w "" -f http://localhost:$port/ready; then
      break;
    else
      echo "kollektivkart@$port Not up after attempt number $attempt, sleeping"
    fi
    if [ "$attempt" -eq 10 ] && ! curl -s -o /dev/null -w "" -f http://localhost:$port/ready; then
      echo "kollektivkart@$port failed to start after 10 attempts"
      exit 1
    fi
  done
done
```

We could easily generalize this, we'll do that later if we discover that we need to reuse it. Restarting kollektivkart generally takes about 10 seconds; our script gives up after 60. That should be fine. If the first container does not come back up after a restart, we'll be at half-capacity. That's fine; we have two containers for the redundancy, not the capacity. The script will fail in that case. We'll have to look into getting some sort of monitoring for that later.

Let's add it to the server by making a task in `roles/kollektivkart/tasks/main.yml`:
```yaml
- name: Set up rolling-restart script
  copy:
    dest: "/home/{{ user }}/rolling-restart"
    src: "rolling-restart"
    owner: "{{ user }}"
    group: "{{ user }}"
    mode: "0744"
```

Now we can configure a quadlet for our job in `roles/kollektivkart/tasks/main.yml`:

```yaml
- name: Set up kollektivkart etl quadlet
  copy:
    dest: "/home/{{ user }}/.config/containers/systemd/kollektivkart-etl.container"
    owner: kollektivkart
    mode: "0600"
    content: |
      [Unit]
      Description=Kollektivkart ETL container
      After=network.target

      [Container]
      Image=ghcr.io/kaaveland/bus-eta:latest
      Volume=/home/{{ user }}/bq_credentials:/bq_credentials:ro
      Environment=GOOGLE_APPLICATION_CREDENTIALS=/bq_credentials
      Entrypoint=/app/.venv/bin/python
      Exec=-m kollektivkart.etl ${PARQUET_LOCATION} --memory-limit-gb 3 --max-cpus 2
      AutoUpdate=registry
      EnvironmentFile=/home/{{ user }}/kollektivkart.conf

      [Service]
      Type=oneshot
      # This critical line lets systemd find the ${PARQUET_LOCATION} env var from this file
      # so we can pass it on the command line in the block above
      EnvironmentFile=/home/{{ user }}/kollektivkart.conf
      SyslogIdentifier=kollektivkart-etl
      CPUQuota=200%
      MemoryMax=4G
      WorkingDirectory=/home/{{ user }}
      ExecStartPost=/home/{{ user }}/rolling-restart
      
      [Install]
      WantedBy=default.target
```

It may look strange that we're passing `--memory-limit-gb` and `--max-cpus`, but the reason for that is to inform [DuckDB](https://duckdb.org) about how much capacity it has. Otherwise, it might detect all the CPU cores and try to use more resources than we've allowed for it. `CPUQuota=200%` doesn't prevent it from seeing how many cores the machine has, it is only a scheduling guarantee. It probably wouldn't hurt to let DuckDB use 33% on each of our six cores, but it seems friendlier to let it use two whole ones. 🤗

The job needs an extra environment variable compared to the webapp, the webapp never accesses BigQuery directly. The `[Service]` section has `ExecStartPost`. This is a somewhat strange name-choice, I think, for a command that is to be run once the script is done. So, this systemd unit will run a container once, then do the rolling restart. But nothing actually starts this container, so we have to take care of that too. We can use a systemd timer for this, let's write it:

```yaml
- name: Set up kollektivkart etl nightly timer
  copy:
    dest: "/home/{{ user }}/.config/systemd/user/kollektivkart-etl.timer"
    owner: "{{ user }}"
    group: "{{ user }}"
    mode: "0600"
    content: |
      [Unit]
      Description=Run Kollektivkart ETL nightly
      RefuseManualStart=false
      RefuseManualStop=false
      [Timer]
      OnCalendar=*-*-* 04:00:00
      RandomizedDelaySec=30m
      Persistent=true
      Unit=kollektivkart-etl.service
      
      [Install]
      WantedBy=timers.target

- name: Enable kollektivkart-etl
  command: machinectl shell {{ user }}@ /bin/systemctl --user enable kollektivkart-etl.timer

- name: Start kollektivkart-etl timer
  command: machinectl shell {{ user }}@ /bin/systemctl --user start kollektivkart-etl.timer
```

This is a lot like a cronjob. We've set it to go off at 04:00, with a randomized delay of up to 30 minutes. It's also set to persistent, which means if the machine is off from 04:00–04:30, it'll decide to run this job once it boots. Let's check if this worked:

```shell
ssh -p2222 kollektivkart@localhost systemctl --user status kollektivkart-etl.timer
● kollektivkart-etl.timer - Run Kollektivkart ETL nightly
     Loaded: loaded (/home/kollektivkart/.config/systemd/user/kollektivkart-etl.timer; enabled; preset: enabled)
     Active: active (waiting) since Tue 2025-05-13 23:16:21 CEST; 2s ago
    Trigger: Wed 2025-05-14 04:07:08 CEST; 9h left
   Triggers: ● kollektivkart-etl.service
```

That looks good! The job itself won't actually work without the correct BigQuery or S3 credentials, but everything's configured now.

## Setting up a test server

We actually have everything we need to make this come alive on the internet now. If you read this far, you have my undying respect. Maybe you learned something?

I'm going to quickly clickops a server in hetzner and point api-test.kaveland.no and kollektivkart-test.kaveland.no to it, then see if everything comes up. I name my personal servers after whisky distilleries. This one is going to be called dalwhinnie.

### DNS

I'm setting up A and AAA records for dalwhinnie.kaveland.no, and putting this in my hosts.ini:

```ini
[test]
dalwhinnie.kaveland.no
[test:vars]
ansible_ssh_user=root # will later need to change to admin after first time provisioning
ansible_become_user=root
```

I'll make CNAME records for api-test.kaveland.no and kollektivkart-test.kaveland.no pointing to dalwhinnie.kaveland.no. 

I'm removing the `secrets.yml` from the playbook and running this:
```shell
ansible-playbook -i hosts.ini --limit test --ask-vault-pass initialize.yml \
  -e @~/code/infra/secrets.yml # reads secrets from the real vault
```

It applies OK to the brand-new server. A few moments later, once caddy has gotten certificates:

```shell
curl -I https://api-test.kaveland.no/app/eugene/random.sql
HTTP/2 200
alt-svc: h3=":443"; ma=2592000
server: Caddy
date: Tue, 13 May 2025 17:22:50 GMT

curl -I https://kollektivkart-test.kaveland.no/
HTTP/2 200
alt-svc: h3=":443"; ma=2592000
content-type: text/html; charset=utf-8
date: Tue, 13 May 2025 17:23:38 GMT
server: Caddy
server: gunicorn
content-length: 4161
```

And we're in business! Caddy works as advertised. It took a minute or so to get certificates. If you notice time-traveling in the timestamps here, don't worry. I'm not making a paradox. I've just rerun some commands above in the late evening. Didn't mean to spook you. 👻

I did a quick reboot here and verified that everything came up, and the kollektivkart-etl job started automatically. The `rolling-restart` script works well enough for my purposes (I observed about 2 seconds of downtime, as expected). I deleted the server afterward. I can trivially make a new one.

## Static assets

I don't host static assets from the server, I rely on bunny.net for that. [Read more here if you'd like.](/posts/2025-04-20-deploying-to-bunnycdn) This costs around $1 a month, for much better worldwide performance than I could ever achieve on a single server. Totally worth it. Bunny also has a container hosting service that would be very suitable for `eugene-web`.

## Monitoring

The way I've set this up, I must expect reboots. At some point, my entire infrastructure could be down. Since I'm planning on running only a single server and could move it around a bit, my best option here is to use something external. 

I've set up a [statuspage](https://kaveland.status.phare.io/) with [phare.io](https://phare.io/). At my level of usage, this is a free service. It pings three different URLs I run every few minutes, and it will email me if they stay down for a while. This was super easy to set up, and works very well. I inadvertently tested this by disabling DNSSEC on my domain before getting rid of the DS record the other day 🫠

It works. Don't be like me, find a more harmless way to test it. For things like my ETL-job, I'll make a URL on my page that returns some status code other than 200 if the data is stale, and phare.io will notify me if the job has had some issue. I don't have a plan right now for detecting that a rolling restart failed, but something will come to me.

For the moment, I do not have anything better than `/var/log/syslog` and `journalctl` for viewing logs, and `sar` for viewing server load and resource consumption over time. That will do for a while, I think, it's not like I get a lot of traffic. 

## Technical debt we could fix

The big one here feels like the proxy setup and the port numbers. Here's what we did wrong:

- Putting the proxy hostname in at the app level.
- Putting the port numbers at the app level.

The hostname and the port numbers are what caddy needs to know about. I think we should probably have made an `proxy-endpoint` role that could connect the two, something like this 🧐

```yaml

roles:
  - name: base-install
  - name: eugene 
    vars:
      ports:
        - 3000
  - name: proxy-endpoint
    vars:
      hostname: "api{{ env_suffix }}.kaveland.no"
      routes:
        - path: /eugene
          ports:
            - 3000
```

We could always consider that later, but it feels like a lot of trouble right now. For such a small setup, the best solution is probably to just use one central Caddyfile.

We should also consider having more playbooks. `initialize.yml` should be more bare-bones than it is, possibly do only the security-related things. That way, we could let it override the initial username to log in with, since we disable ssh access for the `root` user later.

We'll definitely find a reason to generalize the `rolling-restart` script at some point, or perhaps replace it with something that uses the [caddy management api](https://caddyserver.com/docs/api) to drain the backend before we restart it.

We've put image tags directly in the quadlets. That's not a great idea. It means we need to edit complex and annoying files to roll back, possibly while under stress. We should probably put the tag somewhere it's easier to edit. Quadlet files can reference environment files, so this is easily doable.

## Architectural weakness

I currently have my S3 bucket and my server in the same region in Hetzner. This is _only_ okay because I can recreate the data perfectly from an external source. Normally I would advocate _very strongly_ for having data be replicated to other regions. [Data centers can burn down](https://www.pcmag.com/news/ovhcloud-data-center-devastated-by-fire-entire-building-destroyed).

On the whole, there's not a lot of redundancy. If the machine is down, my things are down. The fact that making a new server is fast makes this point less painful. It is straightforward to scale to a bigger machine. It's possible to scale out to more machines too, but that requires tinkering more with DNS, TLS and load-balancing.

There's no persistent database in this setup. I believe I have the chops to set up a reasonably stable postgres installation with [pgBackRest](https://pgbackrest.org/) that ships backups to _elsewhere_ eventually. But hosting a database is no joke, this is something I would advise anyone to consider buying as a service. It might seem expensive, but it's not.

For hobby purposes, I think all of these are non-issues, but I would advise spending more time on a setup like this if I were running a business. Or perhaps accept the cost of buying managed services; there are many that are worth paying for.

## Why go through all this trouble?

I could say that it was about the journey, not the destination. That wouldn't be wrong, exactly. I enjoy tinkering with Linux servers, and I feel like I learned a lot doing this exercise. As a developer, I find myself building on top of leaky abstractions all the time. It is good to know a thing or two about what's underneath whatever abstraction I deploy my software on. This is a fairly lean setup for a machine. I like that.

The liberty to host my stuff wherever I want is important to me right now. Being able to put everything on a Linux server with a simple ansible-playbook makes me very flexible. This kind of deployment is possible at almost any provider, and means I get to test all the european providers I'm interested in. 

There's a fairly large initial time investment, but that's mostly done now. Setting up a new container is going to be rapid and simple in the future, now that all the pieces are in place.

I'm currently running on bare metal, so the price/performance ratio is hard to beat. I have 6 physical CPU cores, 64GB of RAM and 500GB of NVMe SSD at a very reasonable €46.63/month, including VAT. For comparison, this costs significantly less than a 2VCPU 8GB RAM D2_V3 in Azure, and I have no risk of noisy neighbors impeding on my VCPU time. I have no excuses for writing adequately efficient SQL anymore. I must drop all indexes immediately.

If I decide that I have no need for bare metal, I'll go back to 4 VCPU, 8GB RAM and 80GB NVMe SSD at €7.8/month. This is enough to run what I have right now, I just bought something bigger to force me to have bigger ambitions.

If it turns out that there are a lot of issues with running like this, I can find some managed k8s or container solution instead, and I wouldn't have lost anything but time. But the time already paid for itself with increased knowledge and the entertainment of learning new things 🎓🥳

## What did we learn?

Here's a short list:

- `podman` and `systemd` integrate very nicely now.
- quadlet templates are incredibly powerful and elegant! Just the right level of abstraction for this kind of project.
- `Caddy` makes it very trivial to do TLS with letsencrypt.
- `unattended-upgrades` can take care of patching.
- `k8s` and hosting solutions like fly.io or heroku do _a lot_ of heavy lifting for you.
- There's a reason why people are paying good 💸 to have all this stuff be someone else's problem.
- Stateless backends are straightforward and pleasant to self-host 🎉
- Ansible is still alive and kicking, and I even remember some of it. We have barely scratched the surface of what it can do. It's powerful software. I think it has a Hetzner module, and DNS-integration with bunny.net, so it could probably automate the last manual steps too.
- Ansible and Vagrant is a very nice combination for locally developing server configuration.

If you'd like to self-host on your own server, but this setup looks intimidating and complex, I totally get that. You may want to check out options like [coolify](https://coolify.io/) or [dokploy](https://github.com/Dokploy/dokploy).

## Where to go from here?

If you want to play and tinker with this, [all the code](https://github.com/kaaveland/fire-and-forget-linux) is available. I made some minor modifications to make it more convenient to get started, but if you read all the way here, you'll have no trouble finding your way. Proud of you! Give yourself a pat on the back on my behalf.