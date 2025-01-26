+++
title = "Exploring a webapp using psql and pg_stat_statements"
date = "2025-01-06"
modified = "2025-01-20"
tags = ["postgres"]
+++

It's always an exciting day for me when I get access to the source
code for an entirely new application I need to work on. How does it
look inside, how does it work? Sometimes, there's some design
documentation along with it, or operational procedures, or maybe some
developer handbook in a wiki. I do check all of those, but I don't
expect any of those things to accurately describe how the code works,
because they tend to change less frequently. It's also fairly
low-bandwidth, it takes a ton of time to ingest technical text.

But there are tons of tricks we can use to quickly get to
grips with source code, without having to read it from top to
bottom. I find that one useful exercise is to figure out how the
application uses its database. When that database is postgres, there's
a whole lot of cool things I can check with very little effort,
assuming I can manage to start the application locally. One of my
favorites tricks is to use the `\watch` command in `psql`, while
clicking around in the webapp. This helps me establish the visuals
with important tables and domain objects in the code. I find that this
is often more useful than looking at frontend or backend code in
isolation, because it gives me insight that goes through the entire
application vertically.

This is a low-effort high-reward kind of trick, it doesn't always
yield valuable insights, but it takes very little time to try it out
and sometimes, it helps you find important relationships between
visuals and data models, technical debt or operational disasters
waiting to happen. I usually start out by setting up a local
environment to run the application, and make sure that the database
has the
[pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html)
extension enabled. This may require you to run this snippet:

``` sql
create extension pg_stat_statements;
```

Then I will open a terminal window, move it to a dedicated screen and
enter a query a little bit like this:

``` sql
select
  substring( -- truncate queries so they don't fill the entire screen
    -- replace indentation and newlines by a single space
    regexp_replace(query, '\n| +', ' ', 'g'),
    0, 120) as query, -- which part of the query to show,
    calls,
    total_exec_time
from pg_stat_statements order by calls desc limit 30;
```

This selects the 120 first characters of the 30 most commonly executed
queries, together with the amount of calls and how much database
execution time they have accumulated. Then, in `psql`, I can run
`\watch 1` to have this query run once per second. Clicking around in
a webapp while having this running is great for:

- Finding pages with a surprising amount of complexity.
- Discovering instances of the N+1 problem, where the code selects a
  list of IDs, then runs one select for each ID it found, instead of
  fetching everything with a single join.
- Usually you find out what data is needed for authentication and
  authorization, if the webapp does that itself.
- If there are batch jobs or async workflows using the database as a
  queue, you'll see those as well.

Sometimes when I do this, I discover that some pages run an absurd
amount of queries (typically the N+1 problem or pages that need a huge
amount of information). In between just looking around and getting my
bearings, I will frequently reset the statistics using:

``` sql
select pg_stat_statements_reset();
```

This is useful to do for several reasons:

- Sometimes, the application will run a lot of queries on the first
  page load, then cache that information in memory for subsequent
  requests, potentially refreshing it in a batch job.
- Frequently, the amount of information just becomes too great after
  visiting a few pages and clicking a few buttons, and a clean slate
  is necessary to get your bearings.

There are other views that are very useful to observe in a similar
fashion, in particular `pg_stat_user_tables`, where it's interesting
to observe both the amount of reading (`seq_scan`, `seq_tup_fetch`,
`idx_scan`, `idx_tup_fetch`) as well as the amount of writing (the
`n_tup*`columns). This can functionally act as a kind of heat map,
telling you which tables that are the most important across the
application.
