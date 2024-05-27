+++
title = "Using short lived postgres servers for testing"
tags = ["postgres", "testing", "cicd", "eugene"]
date = "2024-05-27"
+++

Database servers are usually long-lived, and important parts of the infrastructure
that we build on. We rarely set them up from scratch, because we have to take
such good care of them over time. I think this causes a lot of people to think
that setting up a database server is some mysteriously difficult ordeal. To be clear,
that's actually true, if you need high availability and a solid recovery point objective.
But there are a lot of use cases where that's overkill, for example short-lived
test environments, or CI/CD pipelines.

## The postgres data directory

A postgres installation is roughly split into two components:

- The binaries, which are usually installed somewhere in `PATH` and are shared across
  the entire server.
- The data directory, which contains the state of the database cluster, including
  all the databases, tables, indexes, configuration and so on. Most binaries in
  the postgres installation accept `-D` or `--pgdata` as an argument to specify
  where to keep the state, or where to start from.

Many times, we run one postgres instance per server, so that this is split is not
obvious to people. I also think that on ubuntu, the default installation is set up
so that there's a postgres instance already set up somewhere under 
`/var/lib/postgresql` and it makes it sort of look like you can only have the one.

But it's really easy to set up a new postgres instance on a server that
has a postgres installation. Here's what you need to do:

```shell
# Create a new directory for the data
mkdir -p /tmp/throwaway-postgres
# Set up the data directory
initdb -D /tmp/throwaway-postgres
# Start postgres in there
pg_ctl -D /tmp/throwaway-postgres start
# Stop it again
pg_ctl -D /tmp/throwaway-postgres stop
```

If you need to configure anything, you can do that in the `postgresql.conf` 
that is generated in the data directory, or you can pass additional arguments
to `pg_ctl` when you start the server. If you prefer to keep postgres in the
foreground in the shell, you can use `postgres -D /tmp/throwaway-postgres` instead
of `pg_ctl start`. If you prefer to use `pg_ctl`, but have to pass options, you
can use `-o` to pass options to the postgres command, for example to run on a
different port, you'd say:

```shell
pg_ctl -D /tmp/throwaway-postgres -o "-p 5433" start
```

This makes it really easy to run many postgres instances on the same server,
and you also don't really need something like docker to run postgres in your
local dev environment. You can just set up a new data directory for each
project, and start and stop the server as you need it, or just run it
in the foreground in the shell. If you do this, you probably want to use
something like [mise](https://mise.jdx.dev/getting-started.html) to make
sure that all developers use the version of postgres that you plan on
using in production.

## I need my instances to have data

What we've learned about the `-D` option makes it really easy to set up
many empty postgres instances. The next hurdle then, would generally be to
populate the instances with some data, so that our tests or applications can
actually use them. My preferred pattern for this is to have a single instance
that is stable and set up with the data that I need, then clone from that to
make new instances. This is also really simple:

```shell
# Either set up PGPASSWORD or use a .pgpass file
export PGPASSWORD=postgres
pg_basebackup -D /tmp/throwaway-postgres \
  --checkpoint=fast --progress \
  --host the-stable-instance -U postgres
pg_ctl -D /tmp/throwaway-postgres -o "-p 5433" start
```

This is a really fast way to set up a temporary postgres instance, even if 
there's a bit of data in `the-stable-instance`. The `pg_basebackup` command
takes a binary snapshot of the `-D` directory of the stable instance, and
replays any transactions that happened during the backup. This shouldn't
take more than a couple of minutes for a small database of 15-30GB, and
you get an exact copy of the stable instance, with users, databases,
configuration, and all the data.

Note that `pg_basebackup` won't work across different major versions of
postgres, or different CPU architectures.

## Making dynamic instances in kubernetes

If you're running in a kubernetes cluster, you can use the same pattern to
set up a new postgres instance in a pod very easily. You'll need to create
a new pod with an `initContainer` that runs `pg_basebackup` to set up the
data directory, then start the postgres instance in the main container. We
do this at my current project to set up complete short-lived environments
for manual testing or demo purposes, and it works really well. It takes
a few minutes to deploy a complete environment with a ~15GB database
instance. It's also a useful trick to test database migrations on a
realistic dataset before deploying them to production.

## This seems like complete overkill for my use case

I think this is overkill if you only have a single database in the
instance, and it doesn't contain a lot of data. At that point, you can
still use this template idea, and maintain a single stable database
in a single database server, then use `create database $uuid template stable_db`
to set up a new database quickly. You can read more about that idea
in a previous blog post [here](/posts/2024-03-10-testing-transactions-that-commit).

## Using it for fun and profit for eugene

For a while now, I've been working on the `eugene trace` command over
at [the eugene repository](https://github.com/kaaveland/eugene), and I've
been pondering how to make it easier for people to get started with it. In
the weekend, I remembered this pattern that I've used many times before,
and I thought maybe `eugene trace` can just bring its own postgres
instance to the party. With the [0.5.0 release](https://github.com/kaaveland/eugene/releases/tag/0.5.0),
it does just that. If you have docker installed, you can run `eugene trace` in
a directory that has flyway-style migrations like this:

```shell
docker run --rm -v $(pwd):/migrations ghcr.io/kaaveland/eugene:0.5.0 trace /migrations
```

There's no setup required and the container is gone when the command finishes.
