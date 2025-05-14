+++
title = "No-ops linux part 2: Hosting a simple container on a lean mean systemd machine"
date = "2025-05-14"
tags = ["cloud", "linux", "ops", "cdn", "duckdb", "caddy", "ansible"]
build = "render"
cascade = { _build = { list = "never", render = "always" } }
+++

This post is part of the series on no-ops linux deployment. The [previous post](/posts/2025-05-13-fire-and-forget-linux-p1) covered local development of linux server configuration and essential configuration. [This installment](/posts/2025-05-14-fire-and-forget-linux-p2) covers a janky podman installation and configures a reverse proxy to send traffic to a simple container deployment. The [final post](/posts/2025-05-14-fire-and-forget-linux-p3) covers a more challenging deployment with jobs and rolling restarts, and discusses the strengths and weaknesses of this approach to hosting.

At the completion of the previous post, we had automatic installation of a functional Ubuntu server with the bare essentials installed. We did this by writing a `base-install` ansible role. There's still a missing ingredient before we can start deploying containers, though!

## It's time to introduce ✨podman✨

`podman` is a tool for running containers. It's CLI-compatible with docker, and has deep and useful integrations with `systemd`, the `init` on most modern Linux installations. I want to use `systemd` to manage my containers for me with [podman systemd units](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html). This has nice features like auto-updating images, takes care of getting the log where I can read it, can restart failed containers and so on. `podman` will also run docker-compose files for you.

Ubuntu 24.04 (codename Noble) ships with podman 4.9, which is a year old and missing some features I want:

- `systemd` template support for quadlet files (we'll get to this, don't worry)
- Some limited support for using k8s YAML with podman (I know I said I wanted to avoid YAML, but this may come in handy)
- Many quality of life improvements to quadlets

Ubuntu 25.04 (codename Plucky) has podman 5.4, which has everything I want, but 25.04 isn't Long Term Support and not available at all cloud providers.

It's a little dirty, but what I'll do is to add the podman package from 25.04. This is not without risk, it could break things in the future. We'll have to hope that grizzled ops veterans avert their eyes and the gods of fortune and luck are with us.

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
- [kollektivkart](https://kollektivkart.arktekk.no/), source code available [here](https://github.com/kaaveland/bus-eta). This is written in Python and DuckDB, and visualizes where delays in norwegian public transit occur. This backend has a "data pond"; it relies on around ~40GB of data in an S3 bucket and runs jobs to keep it updated.

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

Note that this means that the same set of keys will be used for both `admin` and the `app-user` roles. Probably not what we'd want if we were doing anything important! We can pass different sets of keys to the `base-install` and `eugene`, so that you can deploy `eugene` without being allowed `sudo`. But for now, `vagrant provision` is happy again, and it's time to make the `eugene`-specific tasks.

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

> 💡This `[Container]` uses just a _tiny_ subset of what we can set on it. Check the [documentation](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html#container-units-container) to discover more fun settings! You can discover more `[Service]` settings [here](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html). You can read about [AutoUpdate](https://docs.podman.io/en/latest/markdown/podman-auto-update.1.html) too. By default, it'll update containers daily at midnight.

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

So, once we get this on an x86 machine, it'll be fire-and-forget, with systemd and podman taking good care of eugene. Perfect!

`eugene-web` is almost the best-case for something we'll host. It starts in milliseconds and can handle a few hundred requests a second on a single CPU core. We can write many useful applications that are like this! If we can really go a no-ops route here, the CI/CD side of things will just be a pipeline that pushes a docker image. That seems like something we should be able to manage!

Still, it's a little unsatisfactory to only be able to host the simplest possible application. The [next post](/posts/2025-05-14-fire-and-forget-linux-p3) takes a look at something that is a little gnarlier to host, in particular it doesn't restart almost instantly, and it _has a job_ 😧
