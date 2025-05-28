+++
title = "Checking SQL migrations with eugene"
date = "2025-04-16"
tags = ["postgres", "eugene", "rust", "sql"]
+++

It’s been almost a year since I last posted an update on [eugene](https://github.com/kaaveland/eugene/), the CLI tool I’m building to help people write safer SQL migration scripts for postgres. I announced this tool in [Careful with That Lock, Eugene: Part 2](/posts/2024-05-06-careful-with-that-lock-eugene-pt-2). At the time, `eugene` would execute a single SQL script, recording all the locks acquired and warn about possible downtime due to migrations.

It could produce JSON suitable for automated tooling and Markdown suitable for human reading and using in CI comments/checks. That version was already good enough for me to start using in real projects — but it's improved a lot since then, it's now easy to run with almost no setup.

{{< img src="/posts/2025-04-16-whats-up-eugene/img.png" alt="png" >}}


## What's new

- Superfast [syntax analysis](/posts/2024-05-16-linting-postgres-migration-scripts/) for many patterns, to check SQL without running it.
- Proper documentation, with a [demo](https://kaveland.no/eugene/) that can analyze SQL in the browser.
- Git integration, to easily analyze only what's new on a branch.
- Terse terminal-friendly output (JSON and Markdown still supported).
- Support for [temporary postgres](/posts/2024-05-27-shortlived-postgres-servers/) instances to do lock-tracing with zero setup.
- Understanding flyway style naming so it can lock trace migrations in the right order.
- It installs very easily with [mise](https://mise.jdx.dev/) these days! There's even a binary for windows now (I have only tested this in wine, though).
- Guide for [GitHub Actions](https://kaveland.no/eugene/actions.html) and [Gitlab CI](https://kaveland.no/eugene/gitlab.html).
- Many more hints, for example, it can now [suggest new indexes](https://kaveland.no/eugene/hints/E15/unsafe_trace.html#e15-missing-index) and [detect table rewrites](https://kaveland.no/eugene/hints/E10/index.html).

I always use `eugene lint` and `eugene trace` when working on SQL migrations now. It has gotten pretty helpful.
 
## What's coming

I’ve found that working on this tool really sparks joy. There's still so much I want to do. Today I’ve been mulling over the idea of adding a command to connect to a running postgres database and check the schema for antipatterns. For example, identify missing indexes, usage of types that have big drawbacks, such as the `JSON` type. Maybe implement some sort of configuration system to let people ban certain types or patterns and allow others. We could even look up the queries in `pg_stat_statements` to check if there are some obviously bad ideas in there. Joining on incompatible types, for example—type coercion in a join condition will often stop the planner from using indexes. Some of these things would be hard to check from just reading the migration scripts, and straightforward to find by running queries to a postgres instance.

If reading this makes you think of features you want, or it sounds like it would be fun to collaborate on making `eugene`, reach out [at the issue tracker](https://github.com/kaaveland/eugene/issues).

Most of all, I find that developing this tool is a great way of diving deeper into postgres, and learning more. I have learned so many things from working on this! I feel comfortable developing new CLI tools in Rust, it no longer takes me very long. I have a much deeper knowledge of postgres locks and many of the builtin types than before. I know the [system catalogs](https://www.postgresql.org/docs/current/catalogs.html) a lot better.


## Projects to check out

There are also a number of new (to me) and exciting projects I've discovered over the past year.

[Squawk](https://squawkhq.com/) has a huge overlap with what eugene tries to do and looks very mature. The documentation is so good! It's also beautiful. What an excellent resource to know about! Squawk does syntax analysis with `pg_query.rs`, similarly to how `eugene lint` does it.

There's a [postgres language server](https://github.com/supabase-community/postgres-language-server/) project! I have reached out to see if maybe I can [contribute](https://github.com/supabase-community/postgres-language-server/discussions/305) some of what I've learned making eugene.

[pgtemp](https://github.com/boustrophedon/pgtemp) is a really cool way of making ephemeral postgres instances for tests/CI. Under the hood, it uses the same mechanisms as eugene to create instances, but it has a very nifty proxy-solution for isolating connections from each other.

## Conference talk

I got my conference talk about safely using postgres in production accepted at [TDC Trondheim](https://2025.trondheimdc.no/)! This isn't entirely unrelated to eugene, it's a topic that's apparently been on my mind a lot over the past year.


