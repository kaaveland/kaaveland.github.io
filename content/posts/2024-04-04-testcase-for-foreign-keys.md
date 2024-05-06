title: How to test for missing indexes on foreign keys
category: postgres
tags: postgres
date: 2024-04-04
modified: 2024-04-04

If you're developing a transactional application backed by postgres, there's a
pretty cool trick you can use to check if you're missing indexes that could
potentially cause serious performance issues or even outages. In particular, I
mean foreign keys where the referencing side of the constraint does not have an
index. The idea is very simple, we can select all of the columns that take part
in a foreign key, then remove the ones that take part in a complete index, and
the remainder should be the empty set, or possibly match a known allowlist. I
think this is a valuable addition to the test cases for your database
migrations, or if you can't easily do that, maybe in your CI/CD pipeline.

So why is it important to test this? With postgres you get indexes on the
referenced side of a foreign key automatically, since it must be a primary key
or a unique key, isn't that enough? Aren't indexes expensive to maintain?
There's no guarantee that the query planner will even use them.

Indexes do have a cost, they're not free. But I think it's good advice to ignore
that until you have a space problem or a performance on write problem. Space is
very cheap these days and the performance overhead on writes for a regular
b-tree index (the default one) is very low. It's also true that the query
planner may choose to ignore the index for the queries that you care
about. But the cost of not having that index could be so much higher, if the
amount of rows in the table crosses some threshold, or the statistics get
changed somehow, the query plan may change, so that the index is needed at any
time in the future.

In addition, the indexes are used in some non-obvious cases where it can be quite
difficult to identify why transactions are slow. If you're  doing deletes on the
referenced side of the foreign key, or you're updating a column on the
referenced side of the foreign key, postgres will need to validate the
referencing side to preserve referential integrity, and this can take a table
lock. If it does lock the table, it's super important that the validation is
fast, since otherwise unrelated transactions could queue up and possibly time
out, or fail, throwing some hefty fog of war onto the debugging session. It
won't take a very big outage to make the cost of having indexes on foreign keys
seem low. For the same reasons, you should be careful about deleting seemingly
unused indexes on foreign keys.

Here's a query that can be used to find columns that take part in a foreign key,
but aren't covered by a complete index:

``` sql
WITH fk_columns as (
  SELECT
    nsp.nspname AS schema_name,
    tbl.relname AS table_name,
    att.attname AS column_name
  FROM
    pg_constraint con
    INNER JOIN pg_class tbl ON con.conrelid = tbl.oid
    INNER JOIN pg_namespace nsp ON tbl.relnamespace = nsp.oid
    INNER JOIN pg_attribute att ON att.attrelid = tbl.oid AND att.attnum = ANY(con.conkey)
  WHERE
    con.contype = 'f' -- 'f' indicates a foreign key constraint
    AND nsp.nspname NOT IN ('pg_catalog', 'information_schema')
), indexed_columns as (
  SELECT
    nsp.nspname AS schema_name,
    tbl.relname AS table_name,
    att.attname AS column_name
  FROM
    pg_index AS indx
    JOIN pg_class AS tbl ON indx.indrelid = tbl.oid
    JOIN pg_class AS idx ON indx.indexrelid = idx.oid
    JOIN pg_namespace AS nsp ON tbl.relnamespace = nsp.oid
    JOIN pg_attribute AS att ON att.attrelid = tbl.oid AND att.attnum = ANY(indx.indkey)
  WHERE
    indx.indpred IS NULL -- only use total indexes, ie not create index ... where condition
    AND nsp.nspname NOT IN ('pg_catalog', 'information_schema')
), allowlist as (VALUES
  ('public', 'tiny_table', 'tiny_column'),
  ('public', 'ok_table', 'ignore_column')
)
SELECT * FROM fk_columns
  EXCEPT
SELECT * from indexed_columns
  EXCEPT
SELECT * from allowlist;
```

Run it once to either create the missing indexes or amend the whitelist, then
add it to your migration test cases or your regular build, with an assert that
it comes up with the empty set, and you can sleep just a little bit easier at
night.
