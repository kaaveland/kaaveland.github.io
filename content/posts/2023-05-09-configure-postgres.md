title: Protecting your postgres server from your application
category: postgres
date: 2023-05-09
modified: 2023-05-09


There are 2 configuration options that every OLTP application that uses postgres
should set, in order to protect the database from high load:

- `statement_timeout`
- `idle_in_transaction_session_timeout`

These can both be set by client configuration and require no special
permissions to set, and are easily overridden locally for transactions that have
different requirements.


They can be a bit scary to retrofit to existing applications, but we can
activate two postgres extensions to help us measure our queries to find safe
values to set:

- `pg_stat_statements`
- `auto_explain`

It's also a really good idea to monitor how many connections that are actively
used on the database server. You may have integration with a good monitoring
tool on the application side already, but if you don't, you can easily set
up very useful monitoring by sampling the `pg_stat_activity`.

`statement_timeout`
--

The [official documentation](https://www.postgresql.org/docs/current/runtime-config-client.html)
has this to say:

> Abort any statement that takes more than the specified amount of time. If
> log_min_error_statement is set to ERROR or lower, the statement that timed out
> will also be logged. If this value is specified without units, it is taken as
> milliseconds. A value of zero (the default) disables the timeout.

Usually you want to set it in the application configuration, for example in the
connection pool configuration. If you use
[HikariCP](https://github.com/brettwooldridge/HikariCP#infrequently-used) it
makes sense to configure your pool with:

```java
pool.setConnectionInitSql("set statement_timeout = 1000");
```

Any transaction can `set statement_timeout` at any time, so if some queries must
be allowed to run longer, it's easy to apply this setting locally (but remember
to set it back to the default once you're done with the connection). It's not a
good idea to set a database level default or server default, since it may
interfere with migrations or analytical queries.


The effect of this is that any statement that causes a connection to postgres to
be in an active state longer than `statement_timeout` is canceled. This is
important to set because if you don't have it, the database will keep chugging
along even if the application gives up on the query, consuming hardware
resources that might be required to complete other queries, causing everything
to slow down. This kind of problem can be very difficult to debug, because
code paths that aren't really problematic might start failing. It is much easier
to figure out what's wrong if the problematic code path fails quickly.

Suppose the following happens:

1. Some result that needs to be sorted grows too large to be sorted in memory,
   causing the database to sort using temporary files, slowing a query down
   from a few milliseconds to many seconds.
2. A user requests a page that runs this query, and the page appears to hang.
   The user waits a couple of seconds, then tries to refresh the page. This may
   happen more than once.
3. At this point the database has N copies of the problematic query running,
   each using lots of IO capacity. All N copies of the query and all other
   queries that hit disk now contend to get IO time, slowing everything down to
   a crawl. The database does not know that the application isn't interested in
   the result of the first N - 1 copies of the query that the user canceled.

This is what `statement_timeout` protects you against. Even if you set it to a
high value like 2 seconds or 5 seconds, it's still valuable, to prevent 1 user
from being able to use up all database server resources by accident, which they
can easily do if they encounter a page that runs a pathologically bad query.

`statement_timeout` will also cancel transactions that wait a long time to
obtain locks, helping you prevent your connection pool from running out of
connections if you have some accidental locking or queueing for locks.


Setting `idle_in_transaction_session_timeout`
--

This setting terminates connections that have started a transaction that
did not either roll back or commit before the timeout occurs. A typical
case of this might be that the application does some HTTP requests while
holding an open transaction. If the application has taken locks in the database
and forgot to set appropriate HTTP timeouts, this could cause pretty big
problems for other traffic, so it's normally something you'd want to avoid just
to be on the safe side. This setting can also be configured using `set`:

```java
pool.setConnectionInitSql("set statement_timeout = 1000; set idle_in_transaction_session_timeout = 1000");
```

Adding timeouts to an existing application
==

By default both `statement_timeout` and `idle_in_transaction_session_timeout`
are set to `0`, which disables them. If you didn't read up on this before
setting up the application, it might seem very scary to set these up after the
fact. Don't worry though, there are helpful tools in postgres that you can use
to identify good timeout values for your application, although you may need
some help from a DBA to enable them.

There are two very useful postgres extensions that should be fairly
uncontroversial to enable:

[`pg_stat_statements`](https://www.postgresql.org/docs/current/pgstatstatements.html)
--

This extension can track a number of metrics about the queries that your
application actually runs in your database, these are the most useful ones to
know about:

- How many times the query is run
- How much time does it take on average, the highest recorded runtime, the
  standard deviation
- How often does it cause a cache miss or spill something to temp files on disk

If you enable `pg_stat_statements.track_planning`, it will also tell you how
much time it takes to plan the query. You enable this extension in
`postgresql.conf`, for example:

```
shared_preload_libraries = 'pg_stat_statements'
pg_stat_statements.track_planning = on
```

After it has been activated on the server, it needs to be `create`d in the
databases that you plan to monitor:

``` sql
create extension pg_stat_statements
```

There are many ways you can try to use this view to find out if you have queries
that would be impacted by `statement_timeout`. You can reset the stats by
running:

``` sql
select pg_stat_statements_reset();
```

Note that some queries will take a lot longer to execute immedately after a
database restart, because many of the index and table files might not be in
server RAM yet.

[`auto_explain`](https://www.postgresql.org/docs/current/auto-explain.html)
--

This extension serves 2 very useful purposes:

- It will help you identify slow queries
- It will go some way towards telling you why the query is slow by logging the
  query plan

There are a number of options you can configure here:

- `auto_explain.log_min_duration` the threshold, in milliseconds, that causes a
  query to be `explained` in the log
- `auto_explain.log_analyze` enables the `analyze` option of `explain` for the
  output that ends up in the log. In short this will give you the actual row
  counts of the different query plan nodes, and optionally also buffers and
  timing. This can be costly on some hardware.
- `auto_explain.log_timing` enables actual time taken for query plan nodes,
  which is often very useful, but can also be very expensive. It does nothing
  without`auto_explain.log_analyze`. You can disable this to make
  `auto_explain.log_analyze` cheaper.
- `auto_explain.log_buffers` will log enable the `buffers` option for explain,
  helping you identify whether the queries hit disk or read from the buffer
  cache. This does nothing without `auto_explain.log_analyze`.

Configuring both `pg_stat_statements` and `auto_explain` might look like this:

```
shared_preload_libraries = 'pg_stat_statements,auto_explain'
pg_stat_statements.track_planning = on
auto_explain.log_min_duration = '100ms'
auto_explain.log_analyze = on
auto_explain.log_buffers = on
auto_explain.log_timing = off
```

Sampling `pg_stat_activity` for monitoring
--

The [`pg_stat_activity`](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEWhttps://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW)
view is an excellent target for monitoring your connection pools, but since it
represents a snapshot in time, naively sampling it will hide peak connection
usage. To some extent it's possible to improve this by taking samples more often
but it's probably a better idea to make use of the `state_change` column to find
out how many columns that have been idle for the last sampling duration.

Suppose you sample every 10 seconds, then the following query will give you
the count of connections that have been completely idle since the last sampling,
which will help you estimate your free capacity:

``` sql
select count(*)
from pg_stat_activity
where state = 'idle' and now() - state_change <= interval '10 seconds'
```

You can easily add `group by datname, usename` if you have multiple
users/databases on the same database server.

Note that there are a lot of different kinds of problems that may cause increase
usage of connections to the database, but the most common one will be queries
that are run with inefficient query plans, where `auto_explain` is a really good
tool to help you figure out how to fix it.
