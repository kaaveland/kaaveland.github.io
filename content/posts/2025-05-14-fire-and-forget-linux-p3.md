+++
title = "No-ops linux part 3: It puts the data in the pond. Nightly."
date = "2025-05-14T18:00:00Z"
tags = ["cloud", "linux", "ops", "cdn", "duckdb", "caddy", "ansible"]
+++

This post is part of the series on no-ops linux deployment. The [first post](/posts/2025-05-13-fire-and-forget-linux-p1) covered local development of linux server configuration and essential configuration. The [previous installment](/posts/2025-05-14-fire-and-forget-linux-p2) covers a janky podman installation and configures a reverse proxy to send traffic to a simple container deployment. This is the [final post](/posts/2025-05-14-fire-and-forget-linux-p3). It covers a more challenging deployment with jobs and rolling restarts, and discusses the strengths and weaknesses of this approach to hosting.

After the previous post, we know how to deploy a container that requires absolutely no configuration and restarts almost instantly. Most of the applications I work on in my daytime job aren't like that. Let's take a look at a more complex example.

## Introducing the kollektivkart ✨data pond✨

[kollektivkart](https://kollektivkart.arktekk.no) pulls data from Google BigQuery to S3-compatible storage, runs some [DuckDB](https://duckdb.org) queries on it and shows it in a map (somewhat simplified). The data set it pulls from is open data, and documented at [data.entur.no](https://data.entur.no). The [source code](https://github.com/kaaveland/bus-eta) is freely available, so you can steal it if you wish.

This service _could easily_ use a local disk. It pulls down around 20GB of data from BigQuery as partitioned parquet datasets. After crunching everything I find interesting, it occupies around 40GB of space, including around 700 million rows with 21 columns of raw data, 400 million rows with 18 columns of refined data and 6 million rows of aggregated data that can be visualized. This will work fine on even a cheap cloud virtual machine. What a time to be alive. 

It is incredibly nice to make the server stateless, to the degree that I can. This ensures that I can quickly and easily replace the machine with another one. So, that's what I'll do. The jobs and the webapp can both read/write from `s3://` paths or from a local disk. We'll do it on hard-mode and configure it to work with S3, that way, we can move the app to new servers without having to copy files. Jean-Ralphio sings 🎶stateless🎶

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

> 💡A hostgroup can have many hosts in it! Place a new hostname or IP on each line in the block. You can call it anything you'd like, but you'll need to use `$name:vars` to set common variables to those hosts if you need to. With many hosts, running ansible can be slow. If that's a problem for you, there are some useful [tricks you can use](https://www.redhat.com/en/blog/faster-ansible-playbook-execution).

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
2. We publish the port to `127.0.0.1:%i`. The `%i` is where we receive the template parameter. We use it for a port, but it can be anything! Be creative.

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
    if [ "$attempt" -eq 20 ] && ! curl -s -o /dev/null -w "" -f http://localhost:$port/ready; then
      echo "kollektivkart@$port failed to start after 20 attempts"
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

I'm setting up A and AAAA records for dalwhinnie.kaveland.no, and putting this in my hosts.ini:

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

The way I've set this up, I must expect reboots. At some point, my entire infrastructure will be down. Since I'm planning on running only a single server and could move it around a bit, my best option here is to use something external.

I've set up a [statuspage](https://kaveland.status.phare.io/) with [phare.io](https://phare.io/). At my level of usage, this is a free service. It pings three different URLs I run every few minutes, and it will email me if they stay down for a while. This was super easy to set up, and works very well. I inadvertently tested this by disabling DNSSEC on my domain before getting rid of the DS record the other day 🫠 Going to write about everything I learned about DNSSEC from that in the future! 

Phare works fine for DNSSEC-related outages. Take my word for it. You can find a more harmless way to test it!

For things like my ETL-job, I'll make a URL on my page that returns some status code other than 200 if the data is stale, and phare.io will notify me if the job has had some issue. I don't have a plan right now for detecting that a rolling restart failed, but something will come to me.

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
- `k8s` and hosting solutions like fly.io or heroku do _a lot_ of heavy lifting for you. Heavy lifting can be healthy, though! It's good to understand some of the problems they solve.
- There's a reason why people are paying good 💸 to have all this stuff be someone else's problem.
- Stateless backends are straightforward and pleasant to self-host 🎉
- Ansible is still alive and kicking, and I even remember some of it. We have barely scratched the surface of what it can do. It's powerful software. I think it has a Hetzner module, and DNS-integration with bunny.net, so it could probably automate the last manual steps too.
- Ansible and Vagrant are a very nice combination for locally developing server configuration.

If you'd like to self-host on your own server, but this setup looks intimidating and complex, I totally get that. You may want to check out options like [coolify](https://coolify.io/) or [dokploy](https://github.com/Dokploy/dokploy).

## Where to go from here?

If you want to play and tinker with this, [all the code](https://github.com/kaaveland/fire-and-forget-linux) is available. I made some minor modifications to make it more convenient to get started, but if you read all the way here, you'll have no trouble finding your way. Proud of you! Give yourself a pat on the back on my behalf.

There's a list of things to try in the section about technical debt. Here are some more ideas:

- Maybe try running Caddy in a container?
- Check if we can use [socket activation](https://github.com/containers/podman/blob/main/docs/tutorials/socket_activation.md)! This seems like an almost magic way to pass sockets from the host to the container.
- Set up a [podman network](https://github.com/containers/podman/blob/main/docs/tutorials/basic_networking.md)!
- Make an app and deploy it in [Hetzner](https://www.hetzner.com/), then move it to [upcloud](https://upcloud.com/) or [scaleway](https://www.scaleway.com/en/). You can go anywhere now!


If you'd like to refer back to an earlier installment, I placed links here for your convenience:

1. [The first post](/posts/2025-05-13-fire-and-forget-linux-p1) covers local development of linux server configuration and essentials.
2. [The second post](/posts/2025-05-14-fire-and-forget-linux-p2) covers installation of [podman](https://podman.io/) and [caddy](https://caddyserver.com/). It concludes by deploying a very simple stateless webapp in a container.  

Writing this piece took a while. If you read all the way to the end, it would mean the world to me if you'd let me know what you think and perhaps share it with someone. You can find some contact information on my [personal page](https://kaveland.no). If there's any interest, I might do more projects with a scope like this in the future.