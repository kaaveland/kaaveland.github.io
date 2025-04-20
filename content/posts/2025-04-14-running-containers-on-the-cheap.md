+++
title = "Running containers on no-ops linux in 2025"
date = "2025-04-14"
tags = ["cloud", "linux", "ops"]
+++

Back in February, I decided that I wanted to move hosting of my hobby projects to a european cloud provider. At this time, I don't feel like spending more energy on why, but maybe someone can learn something from the how. I have pretty simple requirements, so I figured I should be able to find simple and inexpensive hosting too. It turns out that there are many european cloud providers in 2025, but none that were really a _perfect_ fit for what I was looking for. Here's what I wanted:

- TLS and sensible http routing
- Inexpensive hosting and S3-compatible object storage
- Running arbitrary webapps in containers
- Running arbitrary jobs in containers
- Option to use a managed database if I wanted
- Easy/scriptable deploy, minimal ops, minimal fuss
- CDN
- As little YAML as possible (I do enough of this during office hours)

I didn't find something like this at a price point I was comfortable with for my hobby projects. All the parts are there, but the lego hasn't been assembled just right (yet). After scouring a lot of documentation on different clouds, I decided to just try running it on a linux virtual machine and think about CDN later.

For price, I think it is probably hard to beat [Hetzner](https://www.hetzner.com/). I had also heard from several people I know that they were good before, so that's where I ended up going. There's a [terraform provider](https://github.com/hetznercloud/terraform-provider-hcloud), an [API](https://docs.hetzner.cloud/) and the machines come with [cloud-init](https://cloudinit.readthedocs.io/en/latest/index.html). Hetzner is fairly bare bones, there's few managed services to choose from. I thought it was probably acceptable for me to run with a Linux server. 

I'm happy with Hetzner as a provider, but I also thought [upcloud](https://upcloud.com/) and [scaleway](https://www.scaleway.com/) look promising, so I'll check those out at some point in the future. Unlike Hetzner, both of those have managed kubernetes and managed databases offerings. All of them offer inexpensive S3-compatible object storage and network level load balancers.

## Linux for container workloads in 2025

I feel like I've landed a setup that is good enough for now on the server, and there's some future work on setting up automated deployments. In short, there's a reverse proxy running on the host, proxying to [podman](https://podman.io/) containers managed by [systemd](https://systemd.io/). This is a surprisingly versatile and ops-free setup so far. I've been running on kubernetes at work for around 7 or 8 years now. While it's a great tool, I do get enough of it during office hours and wanted something simpler for my hobby projects. podman has rootless containers, great integration with systemd, and is CLI-compatible with docker. I like it a lot so far.

The server does unattended reboots approximately once a week (when there are security updates), and everything just comes right back up. I feel like a server like this could be _mostly_ automatically set up in cloud-init. I went with Ubuntu 24.04 for my machine.

### Server ops & TLS termination

There's some number of things that need to be done to the server to make it secure and usable. Ideally, I should make a cloud-init script to take care of these, but I haven't yet. Disable passwords in ssh logins:

```shell
echo PasswordAuthentication no >> /etc/ssh/sshd_config.d/require_key.conf
systemctl reload ssh
```

There's a lot more ssh hardening steps I could take, I remember setting up `fail2ban` and alternate ports in the past, as well as a number of configuration options. For now, I've firewalled the server with a Hetzner firewall so that only my IP can reach ssh on port 22. Since I’m not an enterprise and this isn’t mission-critical, I figure this level of SSH security is good enough for my use case.

I ensured unattended upgrades are enabled:

```shell
systemctl enable unattended-upgrades
```

Ensure that unattended upgrades reboot when required by editing `/etc/apt/apt.conf.d/50unattended-upgrades`. In particular, I've found these lines and changed them:

```
// Automatically reboot *WITHOUT CONFIRMATION* if
//  the file /var/run/reboot-required is found after the upgrade
Unattended-Upgrade::Automatic-Reboot "true";

// Automatically reboot even if there are users currently logged in
// when Unattended-Upgrade::Automatic-Reboot is set to true
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";

// If automatic reboot is enabled and needed, reboot at the specific
// time instead of immediately
//  Default: "now"
Unattended-Upgrade::Automatic-Reboot-Time "02:00";

// Enable logging to syslog. Default is False
Unattended-Upgrade::SyslogEnable "true";
```

I chose to use `nginx` as a reverse proxy, because I'm familiar with the arcane configuration language, and it's tried and tested millions of times. I use certbot for TLS, which I'm also familiar with from before. This combination is robust and common, so it's a safe choice.

I would like to check out [caddyserver](https://caddyserver.com/) which seems more modern at some point, so I'm probably changing this later. Maybe I could run it as a container? 🤔 Caddy has letsencrypt-integration builtin and probably more modern defaults.

To set up nginx and certbot, I needed to install:

```shell
apt install nginx certbot python3-certbot-nginx -y
```

I made a site in `/etc/nginx/sites-available/kollektivkart.conf`:

```shell
server {
    server_name kollektivkart.kaveland.no kollektivkart.arktekk.no;
}
```

I enabled it with:

```shell
ln -s /etc/nginx/{sites-available,sites-enabled}/kollektivkart.conf
systemctl reload nginx
```

This is enough to get a certificate with certbot (assuming DNS is set up with A records pointing to the server IP):

```shell
certbot --nginx -d kollektivkart.kaveland.no -d kollektivkart.arktekk.no # prompts for email and accept terms
grep -R certbot /etc/cron* # verify that cert renewal has been set up
rm /etc/nginx/sites-enabled/default # remove the default site now that there's something on the server
```

After running [qualys ssltest](https://www.ssllabs.com/ssltest/) and getting an A, I felt like I had the basic steps needed to set up a new endpoint address. I added some global nginx configuration to `/etc/nginx/conf.d/reverse_proxy.conf` to set timeouts, limits, enable compression and some security options:

```shell
add_header X-Frame-Options "SAMEORIGIN";
add_header X-XSS-Protection "1; mode=block";
add_header X-Content-Type-Options "nosniff";
client_max_body_size 1M;
limit_req_zone $binary_remote_addr zone=request_limit:10m rate=15r/s;
limit_conn_zone $binary_remote_addr zone=conn_limit_per_ip:10m;
client_header_buffer_size 4k;
large_client_header_buffers 2 4k;
keepalive_timeout 15s;
client_body_timeout 15s;
client_header_timeout 15s;
proxy_connect_timeout 5s;
proxy_read_timeout 5s;

gzip_vary on;
gzip_proxied any;
gzip_comp_level 6;
gzip_buffers 16 8k;
gzip_http_version 1.1;
gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

log_format combined_with_ms '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" "$request_time"';
```

### Running a container

I wanted a dedicated linux user for each container. I created a user:

```shell
useradd -m -s /bin/bash kollektivkart
# enable user to own systemd units that are automatically enabled on boot
loginctl enable-linger kollektivkart
```

I installed podman to run containers:

```shell
apt install podman
```

I decided to run this particular container on port 8000 on the loopback, so I went and modified `/etc/nginx/sites-available/kollektivkart.conf`, adding the following into the `server` block that was already there:

```shell
    location = /robots.txt {
        add_header Content-Type text/plain;
        return 200 "User-agent: *\nDisallow: /";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        limit_conn conn_limit_per_ip 20;
        limit_req zone=request_limit burst=20 nodelay;
    }

    access_log /var/log/nginx/access.log combined_with_ms;
```

The rest of the steps have been done with the `kollektivkart` user I created. I made an environment file for environment variables I wanted to be available within the container. There aren't any secrets in this one, so I didn't bother with [podman secrets](https://docs.podman.io/en/latest/markdown/podman-secret-create.1.html) and just created `$HOME/kollektivkart.conf`:

```shell
CPU_LIMIT=2.0
MEM_LIMIT=2048m
WORKERS=4
SIMPLE_ANALYTICS=true
IMAGE_TAG=latest
```

In `$HOME/.config/systemd/user/kollektivkart.service` I made a systemd unit for the container:
```systemd
[Unit]
Description=kollektivkart
After=network.target

[Service]
EnvironmentFile=/home/kollektivkart/kollektivkart.conf
ExecStart=/usr/bin/podman run --rm -p 127.0.0.1:8000:8000 \
      --cpus="${CPU_LIMIT}" \
      --memory="${MEM_LIMIT}" \
      --env-file=/home/kollektivkart/kollektivkart.conf \
      ghcr.io/kaaveland/bus-eta:${IMAGE_TAG} \
      webapp:server \
      --preload \
      --bind 0.0.0.0:8000 \
      --chdir=/app \
      --workers="${WORKERS}"


SyslogIdentifier=kollektivkart
Restart=on-failure

[Install]
WantedBy=default.target
```

I started it and enabled it with these commands:

```shell
systemctl --user daemon-reload
systemctl --user enable kollektivkart
systemctl --user start kollektivkart
```

With this setup, I need to `ssh` to the `kollektivkart` user and execute `podman pull ghcr.io/kaaveland/bus-eta:latest` and `systemd --user restart kollektivkart` to deploy. A rollback requires me to manually set `IMAGE_TAG` in the environment file and issue `systemctl --user daemon-reload && systemctl --user restart kollektivkart`. 

## CDN

I went with [bunny.net](https://bunny.net/) for this and set it up by making an A record point to the CDN and having it pull from my origin server at another domain. It was straightforward to set this up, and quite inexpensive too. I'm probably going to change this setup to just push my static files directly into the CDN and run APIs on a different domain in the future. 🚧

## Conclusion

Of the original requirements:

- TLS and sensible http routing ✅
- Inexpensive hosting and S3-compatible object storage ✅
- Running arbitrary webapps in containers ✅
- Running arbitrary jobs in containers ❓
- Option to use a managed database if I wanted ❌ (not supported in Hetzner)
- Easy/scriptable deploy, minimal ops, minimal fuss ✅ (Could do more here 🚧)
- CDN ✅
- As little YAML as possible ✅ (Only in the GitHub workflows that push images)

I'm quite happy with where I got this, but I want to investigate some things soon:

- [caddyserver](https://caddyserver.com/) for TLS termination, possibly inside a container? 🤔 
- [quadlets](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html)
- [podman auto-update](https://docs.podman.io/en/latest/markdown/podman-auto-update.1.html)
- Push static files to CDN for deployment
- Set up all of this configuration with cloud-init + ansible or puppet (Honestly, it's probably going to be ansible even though I wanted to avoid YAML)
- Putting daily batch data processing in podman + systemd managed containers

The setup feels pretty ergonomic and nice already, though. It is quick and easy for me to deploy a new container service, all I need to do is to allocate a port, add a proxy pass and a systemd unit. No new services need to be purchased, I'm already paying for everything I need, and it's actually more affordable than the hosting I was using before. I'm comfortable configuring postgres on this machine, sending backups to object storage using something like [wal-g](https://github.com/wal-g/wal-g) or [pgbackrest](https://pgbackrest.org/), I've done this kind of thing at work before.

### Cost breakdown

All costs include VAT:

- [CDN](https://bunny.net): $0.5 / month minimum payment covers roughly 40GB for my usage
- CX32 instance with 4 shared VCPU, 8 GB RAM and 80GB NVME SSD including backups: € 10.08
- S3 compatible blob storage with 1TB storage and 1TB egress: € 6.24

This is a lot more capacity than what I really need, but it's nice to have some space to grow. Maybe I'll end up hosting more things now that I no longer need to increase the size of my bill whenever I want to test an idea?
