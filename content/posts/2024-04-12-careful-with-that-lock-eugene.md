title: Careful with That Lock, Eugene
category: postgres
date: 2024-04-12
modified: 2024-04-12

It is rewarding to work on software that people care about and use all around
the clock. This constant usage means we can't simply take the system offline for
maintenance without upsetting users. Therefore, techniques that allow us to
update the software seamlessly without downtime or compromising service
quality are incredibly valuable.

Most projects I've worked on use a relational database for persistence, and have
some sort of migration tool like flyway or liquibase to make changes to the
database schema. This post is about a particular kind of migration situation
that, in my experience, most developers who work on such projects will encounter
at some point in their career. They will want to apply a simple, and seemingly
innocent migration, like adding a column to a table and it'll cause some number
of requests to fail, or maybe even a small outage. There are some tricks we can
use here to reduce risk and automatically detect some patterns that cause this
problem.

## Scenario 1


We'll use postgres to describe the setup and scenario, with the following simple
schema:

``` sql
CREATE TABLE documents(id serial PRIMARY KEY, document text);
```

This scenario has 2 transactions in it:

- `A` is a transaction that wants to complete 2 statements, one fast and one
  slow, both modifications to the database.
- `B` is a transaction that only wants to read a single document.

I will start these in different `psql` shells and we'll take a look at what
happens.

### `A` adds a column to `documents`

``` sql
postgres=# BEGIN;
BEGIN
postgres=*# ALTER TABLE documents ADD COLUMN is_indexed bool;
ALTER TABLE
```

`A` is now holding an `AccessExclusiveLock` on `documents`, and all subsequent
transactions that attempt to do anything with that table must wait:

``` sql
postgres=# SELECT l.relation::regclass AS object_name, l.mode, locktype, granted
FROM pg_locks l
JOIN pg_class c ON c.oid = l.relation
JOIN pg_namespace n ON n.oid = c.relnamespace
AND n.nspname != 'pg_catalog';
 object_name |        mode         | locktype | granted
-------------+---------------------+----------+---------
 documents   | AccessExclusiveLock | relation | t
(1 row)
```

### `A` starts a slow statement

Let's say, then that `A` starts a slow statement, like filling in all the
missing values for the new column (suppose that `documents` is a big table):

``` sql
postgres=*# UPDATE documents SET is_indexed = true;
```

### `B` attempts to read a single document

``` sql
postgres=# BEGIN;
BEGIN
postgres=*# SELECT document FROM documents WHERE id = 3;
```

`B` is now blocked and must wait for `A` to finish:

``` sql
# SELECT l.relation::regclass AS object_name, l.mode, locktype, granted
FROM pg_locks l
JOIN pg_class c ON c.oid = l.relation
JOIN pg_namespace n ON n.oid = c.relnamespace
AND n.nspname != 'pg_catalog';
  object_name   |        mode         | locktype | granted
----------------+---------------------+----------+---------
 documents_pkey | RowExclusiveLock    | relation | t
 documents      | RowExclusiveLock    | relation | t
 documents      | AccessExclusiveLock | relation | t
 documents      | AccessShareLock     | relation | f
(4 rows)
```

Once `A` commits successfully, `B` immediately executes. In this scenario, if
`B` is a very frequent transaction type and `A` is very slow, this can seem like
a partial outage that can impact users on the live system.

This scenario is essentially identical to one in which there's a single
migration statement that requires an `AccessExclusiveLock` _and_ performs a
table rewrite, such as adding a `NOT NULL` column with a `DEFAULT` value.

But at least if `A` is fast, nothing bad can happen, right? Well...

## Scenario 2

This scenario has 3 transactions in it:

- `A` is a slow transaction. It reads `documents` and puts all the documents
  somewhere, possibly a search engine or something. The search engine is having
  a particularly bad day today or perhaps `A` is just reading more data than it
  should.
- `B` is our migration. It wants to add a column to `documents`, so that the job
  that runs `A` can see which documents that have already been sent to the
  search engine.
- `C` represents one of many fast transactions, needle-in-the-haystack kind of
  transactions. For example users that have clicked a link from the search
  engine and want to retrieve the entire document to read it, instead of the
  summary from the search engine.

There's a particular interleaving of these that could cause a lot of `C`
transactions to block, leading to time outs or hanging web pages and frustrated
users.

### `A` reads `documents`

``` sql
postgres=*# SELECT document FROM documents;
  document
-------------
 Imagine
 a
 bunch
 of
 interesting
 documents
(6 rows)
```

At this point, A starts doing a bunch of indexing into a search engine, and it's
going to take a long time.

### `B` attempts to take an `AccessExclusiveLock`

``` sql
postgres=# BEGIN;
BEGIN
postgres=*# ALTER TABLE documents ADD COLUMN is_indexed boolean;
```

This transaction is blocked because `A` has some locks that are in conflict with
the `AccessExclusiveLock` on `documents` that `B` is trying to take. We can
check `pg_locks` to see what the status is right now:

``` sql
postgres=# SELECT l.relation::regclass AS object_name, l.mode, locktype, granted
FROM pg_locks l
JOIN pg_class c ON c.oid = l.relation
JOIN pg_namespace n ON n.oid = c.relnamespace
AND n.nspname != 'pg_catalog';
  object_name   |        mode         | locktype | granted
----------------+---------------------+----------+---------
 documents_pkey | AccessShareLock     | relation | t
 documents      | AccessShareLock     | relation | t
 documents      | AccessExclusiveLock | relation | f
```

The two `AccessShareLock`s are held by `A`, which is slow and `B` is waiting for
the `AccessExclusiveLock`.

### `C` attempts to read one row from `documents`

``` sql
postgres=# BEGIN;
BEGIN
postgres=*# SELECT document FROM documents where id = 3;
```

`C` is now blocked, waiting to acquire an `AccessShareLock`:

``` sql
postgres=# SELECT l.relation::regclass AS object_name, l.mode, locktype, granted
FROM pg_locks l
JOIN pg_class c ON c.oid = l.relation
JOIN pg_namespace n ON n.oid = c.relnamespace
AND n.nspname != 'pg_catalog';
  object_name   |        mode         | locktype | granted
----------------+---------------------+----------+---------
 documents_pkey | AccessShareLock     | relation | t
 documents      | AccessShareLock     | relation | t
 documents      | AccessExclusiveLock | relation | f
 documents      | AccessShareLock     | relation | f
(4 rows)
```

At this point, `B` can't proceed because of `A` and `C` can't proceed because of
`B`. If `B` aborts and rolls back, all instances of `C` will be able to
proceed. If `A` is fast enough, it might be that nobody notices anything, if
it's also true that `B` is fast. If `A` is slow enough, some people might
start getting alerts and start an investigation before `A` commits.

## Mitigations

Scenario 1 would be resolved if we made `A` from that scenario into 2
migrations; the `SELECT document FROM documents WHERE id = 3` transaction does
not conflict with the locks that `UPDATE documents SET is_indexed = true` takes.

For the common example of wanting to add a `NOT NULL`-column, we can add the
column without the `NOT NULL` constraint, but with the default value in a
migration. This is pretty much instant. Then we can issue a second migration to
populate the value (it's safer still if we can do this in small batches to avoid
long-running transactions), then a third migration to add the `NOT NULL`
constraint.

Scenario 2 needs a different strategy. Maybe we can design the job so we can
solve the problem by adding a new `documents_index_status` table that has a
foreign key to `documents`?

Once you know these patterns, it's easy to test how possible mitigations would
work out by practicing with concurrent sessions and see what works and what
blocks. What would be very nice however, would be to have some tooling that told
you that you were about to do something potentially dangerous.

## Detection in CI/CD

Recently I learned from a colleague that flyway has a very cool
[callback](https://javadoc.io/doc/org.flywaydb/flyway-core/latest/org/flywaydb/core/api/callback/Callback.html)
feature that will let you run queries in the same transaction as your
migrations, and I'm realizing that there is a _lot of_ potential to build nice
tooling with this feature. I have taken a stab at detecting migrations that take
`AccessExclusiveLock`s on tables that aren't new. I do this in three steps.

### Snapshot `pg_class` before migration

When flyway gives my callback the `BEFORE_EACH_MIGRATE` event, I take a snapshot
of `pg_class` to temporarily store which relations that existed before the
migration ran:

``` sql
CREATE TABLE pg_class_before_migrate as SELECT * FROM pg_class;
```

The reason we do this is that we don't want to yell wolf when migrations create
new tables or indexes, since the locks only matter if other transactions try to
use the relations concurrently with the migration.

### Find relation level `AccessExclusiveLock`s

On the `AFTER_EACH_MIGRATE` event, I retrieve all relation level locks that my
transaction has taken on database objects that existed _before_ the migration
ran. If the migration has issued a `SET ROLE` we may need to change role back to
the one that created the `pg_class_before_migrate`-table.

``` sql
SELECT n.nspname::text AS schema_name, l.relation::regclass::text AS object_name
FROM pg_locks l
  JOIN public.pg_class_before_migrate c ON c.oid = l.relation
  JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE l.locktype = 'relation'
  AND l.mode = 'AccessExclusiveLock'
  AND l.pid = pg_backend_pid(); -- Locks held by current transaction
```

### Clean up

We probably shouldn't leave that snapshot of `pg_class` hanging around forever:

``` sql
DROP TABLE pg_class_before_migrate;
```

At this point, you can choose to have the CI/CD comment on the pull request that
the migration will lock `documents` and therefore you should check what types of
transactions that may try to use that table concurrently with the
migration. Possibly have some LLM generate a helpful text about what could go
wrong with the migration script? Maybe match the locks against a list of
tables that are acceptable to lock, or a list of tables that are known to be
dangerous to lock?

## Future work

Note that there are lots of corner cases still here, I'm very enthusiastic about
lots of ideas in this space and definitely want to write and share some more
code once I know more about what's possible.

Taking a snapshot of `pg_class` potentially also gives us another few things we
can detect. If we can run these migrations against something like an anonymized
copy of the production database, we may be able to issue `ANALYZE` before and
after the migration to detect some table rewrites -- such an operation _should_
change the relationship between `reltuples` and `relpages` in `pg_class`, by
increasing the size of the tuples. That might also allow us to flag migrations
that rewrite large tables. We can also snapshot other tables from
`information_schema`, or tables like `pg_attribute` to build a pretty good data
structure describing the effect of the migration in terms of both schema and
content.
