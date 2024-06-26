+++
title = "Careful with That Lock, Eugene: Part 2"
tags = ["postgres", "rust", "eugene"]
date = "2024-05-06"
aliases = ["/careful-with-that-lock-eugene-part-2.html"]
+++

A while back, I wrote
[Careful with That Lock, Eugene](/posts/2024-04-12-careful-with-that-lock-eugene) about an
idea for how to check if a database migration is likely to disturb production.
That post came about after having an inspiring chat with a colleague about
the advantages of transactional migration scripts and the ability to check
the postgres system catalog views before committing a transaction.

Over the past few weeks, I've been experimenting with this idea to test if I can
use it to build valuable safety checks for DDL migrations. Kind of like
[shellcheck](https://www.shellcheck.net/), but for database DDL migrations.

At this point, I've made enough progress to share some results.
I've been working on a Rust project that compiles a command line tool named
`eugene` and published it to [crates.io](https://crates.io/crates/eugene)
and `ghcr.io/kaaveland/eugene`. The code lives in
[kaaveland/eugene](https://github.com/kaaveland/eugene) and there's a hacker
news thread [here](https://news.ycombinator.com/item?id=40291241).

This post is about what `eugene` can do, how it is implemented, and what I hope
to achieve with it in the future.

## Demo: `eugene trace` report

Suppose I have a migration script named `alter_column_not_null.sql` that looks like
this:

```sql
-- alter_column_not_null.sql
-- create table books(id serial primary key, title text);
-- fix: the title column should be not null
alter table books alter column title set not null;
-- fix: the title column should be unique
alter table books add constraint title_unique unique (title);
```

There exists some table `books` already, and we want to enforce both that the `title`
column is `not null` and that it is unique. Suppose you commit this to a branch and
make a pull request, then a minute later, the pull request is updated with a comment
generated by `eugene trace -f markdown alter_column_not_null.sql` that looks like this:

<div style="border-top: 1px dashed; border-bottom: 1px dashed;">

## Statement number 1 for 10 ms

### SQL

```sql
alter table books alter column title set not null;
```

### Locks at start

No locks held at the start of this statement.

### New locks taken

| Schema   | Object  | Mode                  | Relkind | OID | Safe |
|----------|---------|-----------------------|---------|-----|------|
| `public` | `books` | `AccessExclusiveLock` | Table   | 1   | ❌    |

### Hints

#### Validating table with a new `NOT NULL` column

ID: `make_column_not_nullable_with_lock`

A column was changed from `NULL` to `NOT NULL`. This blocks all table access until all rows are validated. A safer way is: Add a `CHECK` constraint as `NOT VALID`, validate it later, then make the column `NOT NULL`.

The column `title` in the table `public.books` was changed to `NOT NULL`. If there is a `CHECK (title IS NOT NULL)` constraint on `public.books`, this is safe. Splitting this kind of change into 3 steps can make it safe:

1. Add a `CHECK (title IS NOT NULL) NOT VALID;` constraint on `public.books`.
2. Validate the constraint in a later transaction, with `ALTER TABLE public.books VALIDATE CONSTRAINT ...`.
3. Make the column `NOT NULL`


#### Taking dangerous lock without timeout

ID: `dangerous_lock_without_timeout`

A lock that would block many common operations was taken without a timeout. This can block all other operations on the table indefinitely if any other transaction holds a conflicting lock while `idle in transaction` or `active`. A safer way is: Run `SET lock_timeout = '2s';` before the statement and retry the migration if necessary.

The statement took `AccessExclusiveLock` on the Table `public.books` without a timeout. It blocks `SELECT`, `FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE`, `FOR KEY SHARE`, `UPDATE`, `DELETE`, `INSERT`, `MERGE` while waiting to acquire the lock.

## Statement number 2 for 10 ms

### SQL

```sql
alter table books add constraint title_unique unique (title);
```

### Locks at start

| Schema   | Object  | Mode                  | Relkind | OID | Safe |
|----------|---------|-----------------------|---------|-----|------|
| `public` | `books` | `AccessExclusiveLock` | Table   | 1   | ❌    |

### New locks taken

| Schema   | Object  | Mode        | Relkind | OID | Safe |
|----------|---------|-------------|---------|-----|------|
| `public` | `books` | `ShareLock` | Table   | 1   | ❌    |

### Hints

#### Running more statements after taking `AccessExclusiveLock`

ID: `holding_access_exclusive`

A transaction that holds an `AccessExclusiveLock` started a new statement. This blocks all access to the table for the duration of this statement. A safer way is: Run this statement in a new transaction.

The statement is running while holding an `AccessExclusiveLock` on the Table `public.books`, blocking all other transactions from accessing it.

#### Creating a new index on an existing table

ID: `new_index_on_existing_table_is_nonconcurrent`

A new index was created on an existing table without the `CONCURRENTLY` keyword. This blocks all writes to the table while the index is being created. A safer way is: Run `CREATE INDEX CONCURRENTLY` instead of `CREATE INDEX`.

A new index was created on the table `public.books`. The index `public.title_unique` was created non-concurrently, which blocks all writes to the table. Use `CREATE INDEX CONCURRENTLY` to avoid blocking writes.

#### Creating a new unique constraint

ID: `new_unique_constraint_created_index`

Found a new unique constraint and a new index. This blocks all writes to the table while the index is being created and validated. A safer way is: `CREATE UNIQUE INDEX CONCURRENTLY`, then add the constraint using the index.

A new unique constraint `title_unique` was added to the table `public.books`. This constraint creates a unique index on the table, and blocks all writes. Consider creating the index concurrently in a separate transaction, then adding the unique constraint by using the index: `ALTER TABLE public.books ADD CONSTRAINT title_unique UNIQUE USING INDEX public.title_unique;`

#### Taking dangerous lock without timeout

ID: `dangerous_lock_without_timeout`

A lock that would block many common operations was taken without a timeout. This can block all other operations on the table indefinitely if any other transaction holds a conflicting lock while `idle in transaction` or `active`. A safer way is: Run `SET lock_timeout = '2s';` before the statement and retry the migration if necessary.

The statement took `ShareLock` on the Table `public.books` without a timeout. It blocks `UPDATE`, `DELETE`, `INSERT`, `MERGE` while waiting to acquire the lock.

</div>

# How to perform this change safely

`eugene` has some concrete suggestions for changes we could do to make this migration safer. We should
always use `lock_timeout` when taking locks, and here's a way to perform this migration in more steps
that causes less time with dangerous locks held overall. The hints give us a strategy to perform the
migration in several more steps:

## Step 1: Add a `CHECK` constraint that is `NOT VALID`

This still takes the `AccessExclusiveLock` on `books`, but it no longer needs to validate all the rows,
so the lock should be held for a shorter time. All inserts or updates on `books` will only allow
`title` to be `not null`.

```sql
set lock_timeout = '2s';
alter table books add constraint title_not_null check (title is not null) not valid;
```

## Step 2: Validate the constraint

This will take a `ShareUpdateExclusiveLock` on `books`, which is less restrictive than
the `AccessExclusiveLock`. This is possible, because only "old rows" could possibly be
`null`, so there's no need to guard against inserts or updates with a lock.

```sql
set lock_timeout = '2s';
alter table books validate constraint title_not_null;
```

## Step 3: Make the column `not null`

At this point, postgres already knows that `title` is not null, so the `AccessExclusiveLock` is
only necessary for updating the catalog, which is instant:

```sql
set lock_timeout = '2s';
alter table books alter column title set not null;
```

## Step 4: Add the unique constraint concurrently

This returns immediately, and postgres will build up the index and validate the constraint
in its own time, generally without blocking other operations:

```sql
create unique index concurrently title_unique_idx on books(title);
```

## Step 5: Add the unique constraint using the index

This is also instant now, since the index is already built and postgres knows that `title` is unique.
The `AccessExclusiveLock` is again only necessary for updating the catalog:

```sql
set lock_timeout = '2s';
alter table books add constraint title_unique unique using index title_unique_idx;
```

## Summary

In this instance, `eugene` was able to provide some valuable hints about how to make migrations
that achieve the same result, but is much less likely to cause disturbances in the database.

There are many example migration scripts and reports like this in the
[examples](https://github.com/kaaveland/eugene/blob/main/examples/) directory of the repository.

## When do you need a tool like `eugene`?

Breaking small database changes into this many steps isn't for everyone. I have worked on many
systems where we did migrations all the time without using safeguards like this, and most of
the time, it was fine. In many cases, some amount of downtime was acceptable and we could stop
the application prior to running DDL. In many other cases, `lock_timeout` alone would have
saved us from issues with slow concurrent transactions and lock queues.

There is a lot of value in simplicity and simple migration scripts if you can afford it. Here
are some things you may need to deal with if you use the safer approach recommended by
eugene:

- If your statements are unable to take their locks in 2 seconds, your script crashes. You
  may need retries around your migration deployment.
- Creating indexes concurrently can take a long time. The statement returns right away
  and you need to wait for it to finish before you can run the next migration. You must be
  prepared to handle a deadlock or unique violation that makes it unable to complete
  the index.
- Invariably, working like this is going to make you create a lot more migration scripts
  than you otherwise would have.

But if you'd like to learn more about how postgres locking works, and how to avoid common pitfalls
when doing migrations, `eugene` can be a valuable tool. If you're working on a system where
some tables are very large, or have a lot of concurrent transactions where some are slow, `eugene`
could help you avoid "stopping the world" in production when you're executing migrations.

On the whole, I've certainly learned a lot about how postgres works while making `eugene`,
and I hope that I can impart some of that learning on others by seeing the tool adopted.

# How does `eugene trace` work?

`eugene` has a lot of static data built into it. For example:

- It knows about which lock modes that conflict with each other, I've lifted this from the
  excellent [postgres documentation](https://www.postgresql.org/docs/current/explicit-locking.html)
  about locks.
- It has lots of helpful text snippets that can be used to generate hints. I've lifted many of
  these from the awesome [strong_migrations](https://github.com/ankane/strong_migrations) README.

But the primary mechanism that it uses is to break down the SQL script into individual
statements, that are then run in a transaction. Before and after each statement, important
database state is saved in memory, which enables us to calculate the effect that the statement
had on several important system views in the database:

- `pg_class` helps eugene figure out which database objects that are _visible_ to other transactions (and maybe in the future, which objects that have been rewritten).
- `pg_locks` helps eugene figure out which locks that it owns
- `pg_attribute` helps eugene figure out which schema changes that were made to tables
- `pg_constraint` helps eugene figure out which constraints that were added, altered or removed

This means that there's a lot of knowledge that `eugene` does _not_ need to have, for example, it does
not need a very good SQL parser, or keep track of which versions of postgres that exhibits what behaviour.
If postgres 17 will be able to add constraints with lesser locks, `eugene` will be able to figure that out.

Running the transaction, then optionally committing it results in a big data structure that essentially is
a layered diff of database state. `eugene trace -f json` can emit this structure, so that it could be used
by tools like `jq`, or `eugene trace -f md` can generate a markdown report like the one above. Both of
these are essentially just views of this layered diff.

## How are hints implemented?

It is easy to add new hints to `eugene`. They consist of a lot of static text, and then a rule that
checks a statement level diff for certain conditions. If the conditions are met, the hint is emitted.
Here's an example of a hint rule for the `running_statement_while_holding_access_exclusive` hint:

```rust
fn running_statement_while_holding_access_exclusive(
    sql_statement_trace: &FullSqlStatementLockTrace,
) -> Option<String> {
    let lock = sql_statement_trace
        .locks_at_start
        .iter()
        .find(|lock| lock.mode == "AccessExclusiveLock")?;

    let help = format!(
        "The statement is running while holding an `AccessExclusiveLock` on the {} `{}.{}`, \
                blocking all other transactions from accessing it.",
        lock.relkind, lock.schema, lock.object_name,
    );
    Some(help)
}
```

Here's another one for discovering columns that changed from `NULL` to `NOT NULL`:

```rust

fn make_column_not_nullable_help(
    sql_statement_trace: &FullSqlStatementLockTrace,
) -> Option<String> {
    let column = sql_statement_trace
        .altered_columns
        .iter()
        .find(|column| !column.new.nullable && column.old.nullable)?;

    let table_name = format!("{}.{}", column.new.schema_name, column.new.table_name);
    let col_name = column.new.column_name.as_str();
    let help = format!(
            "The column `{col_name}` in the table `{table_name}` was changed to `NOT NULL`. \
            If there is a `CHECK ({col_name} IS NOT NULL)` constraint on `{table_name}`, this is safe. \
            Splitting this kind of change into 3 steps can make it safe:\n\n\
            1. Add a `CHECK ({col_name} IS NOT NULL) NOT VALID;` constraint on `{table_name}`.\n\
            2. Validate the constraint in a later transaction, with `ALTER TABLE {table_name} VALIDATE CONSTRAINT ...`.\n\
            3. Make the column `NOT NULL`\n",
        );
    Some(help)
}

```

I am hoping for some help to add many more to [hints.rs](https://github.com/kaaveland/eugene/blob/main/src/hints.rs)
in the future, I am certain that there are many kinds of migration patterns that I do not know about. If you install
the tool, you can run `eugene hints` to display general information about the hints that it knows about, for example:

```javascript
{
  "hints": [
    {
      "id": "validate_constraint_with_lock",
      "name": "Validating table with a new constraint",
      "condition": "A new constraint was added and it is already `VALID`",
      "effect": "This blocks all table access until all rows are validated",
      "workaround": "Add the constraint as `NOT VALID` and validate it with `ALTER TABLE ... VALIDATE CONSTRAINT` later"
    } // and many more
  ]
}
```

# Where to get `eugene`

You can install `eugene` from [crates.io](https://crates.io/crates/eugene) using `cargo install eugene --bin`,
or you can use the docker image `ghcr.io/kaaveland/eugene` to run the tool. I have been trying to document
it well in the [github repository](https://github.com/kaaveland/eugene). If you want to play around with
it, I suggest you clone the repository. There is a `docker-compose.yml` that boots up a postgres database
which is compatible with the example migrations in `examples/`, so this should get you started:

```shell
docker-compose up -d # boots postgres on 5432
cargo run trace -f markdown examples/alter_column_not_null.sql \
  glow # glow renders markdown in the terminal beautifully
```

If you make any changes to the source code, you can run `cargo test` to run the tests, and see
the diff on all of the markdown files in `examples/` to see the effect of your change.

The test setup is using another neat postgres trick from
[this blog](/isolating-integration-tests-that-commit-transactions.html) to make sure that the tests
can run DDL changes in parallel without conflicting with each other or causing deadlocks.

Once you're satisfied with your changes, you can run `cargo install --path . --bin` to install the
the tool to your system and try it out on your own migrations.

# Future work

I have a lot of ideas for how to improve `eugene`. Here are some of them:

- Add more hints. I am hoping for ideas on the [issue tracker](https://github.com/kaaveland/eugene/issues)
- Read and parse `pg_stat_statements` to find out which queries that could conflict with migrations.
- Add a `eugene ci` command that is suitable for integration with CI/CD pipelines, like pull requests
  so that you can run `eugene ci` on a branch and get a report on the pull request.
- Adding mechanisms to make `eugene` work like a linter, so it can optionally "fail the build".
- Add detection of table and index rewrites, so `eugene` can tell you if a migration could take an
  unexpectedly long time.
- Automatically generate safer migration scripts where it is possible to do this in a deterministic
  manner.

I am hoping to get some feedback on the tool, and I would love some suggestions on the issue tracker for
where to go from here.
