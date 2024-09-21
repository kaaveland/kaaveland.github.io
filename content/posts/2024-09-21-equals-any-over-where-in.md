+++
title = "Consider using array operators over the SQL in operator"
date = "2024-09-21"
tags = ["postgres", "jdbc", "sql"]
+++

In my post about [batch operations](/posts/2024-08-30-multi-selecting-by-composite-key/), I used the
`where id = any(:ids)` pattern, with `ids` bound to a JDBC array. I've gotten questions about that 
afterwards, asking why I do it like that, instead of using `in (:id1, :id2, ...)`. Many libraries
can take care of the dynamic SQL generation for you, so often you can just write `in (:ids)`, just
like the array example. I would still prefer to use the `= any(:ids)` pattern, and I decided to write
down my reasoning here.

It has nothing to do with query performance. These two queries have the same query plan and should
have the same time cost to execute for the database:

```sql
postgres=# explain select sum(cost) from orders where id in (1, 2, 3, 4);
QUERY PLAN
--------------------------------------------------------------------------------
 Aggregate  (cost=17.13..17.14 rows=1 width=8)
   ->  Bitmap Heap Scan on orders  (cost=8.65..17.12 rows=4 width=4)
         Recheck Cond: (id = ANY ('{1,2,3,4}'::integer[]))
         ->  Bitmap Index Scan on orders_pkey  (cost=0.00..8.65 rows=4 width=0)
               Index Cond: (id = ANY ('{1,2,3,4}'::integer[]))
(5 rows)

postgres=# explain select sum(cost) from orders where id = any('{1, 2, 3, 4}');
QUERY PLAN
--------------------------------------------------------------------------------
 Aggregate  (cost=17.13..17.14 rows=1 width=8)
   ->  Bitmap Heap Scan on orders  (cost=8.65..17.12 rows=4 width=4)
         Recheck Cond: (id = ANY ('{1,2,3,4}'::integer[]))
         ->  Bitmap Index Scan on orders_pkey  (cost=0.00..8.65 rows=4 width=0)
               Index Cond: (id = ANY ('{1,2,3,4}'::integer[]))
(5 rows)
```

Parsing SQL is really, really fast. Over at [eugene](https://kaveland.no/eugene/) I host
a tiny service that parses SQL queries to look for dangerous migrations. From time to time, 
people post colossal SQL scripts to it, and parsing is at most a few milliseconds. But it
is theoretically true that parsing a query with a lot of placeholders in 
`where id in (?, ?, ...)` is more expensive. There could be differences in how much time
it takes to actually bind the parameters, or parse the bound array from the wire protocol,
but these are probably negligible in most cases. They are certainly unlikely to be the reason
why you need to look at the query and optimize it.

## What's the big win then?

You get the same query every time. This may sound a little simple, and it's not obvious that this
is important. But it matters once you're running in production and need to follow up performance
over time. This makes it practical to track the query in your telemetry, database logs and in
extensions such as `pg_stat_statements`. It'll produce exactly one row of aggregated performance 
data in `pg_stat_statements`, instead of a number of entries equal to the observed number of 
placeholders in the `where id in (?, ..., ?)` clause. Here's an example of data from 
`pg_stat_statements` where I ran both queries four times with the same parameters:

```sql
postgres=# select query, calls, mean_exec_time from pg_stat_statements where query like '%from orders%';
-[ RECORD 1 ]--+----------------------------------------------------------
query          | select sum(cost) from orders where id in ($1, $2)
calls          | 1
mean_exec_time | 0.115168
-[ RECORD 2 ]--+----------------------------------------------------------
query          | select sum(cost) from orders where id in ($1)
calls          | 1
mean_exec_time | 0.129291
-[ RECORD 3 ]--+----------------------------------------------------------
query          | select sum(cost) from orders where id in ($1, $2, $3, $4)
calls          | 1
mean_exec_time | 0.122043
-[ RECORD 4 ]--+----------------------------------------------------------
query          | select sum(cost) from orders where id = any($1)
calls          | 4
mean_exec_time | 0.19074100000000002
-[ RECORD 5 ]--+----------------------------------------------------------
query          | select sum(cost) from orders where id in ($1, $2, $3)
calls          | 1
mean_exec_time | 0.197209
```

Note how the `= any($1)` query has four calls, but there's four variants of the `in` query. Since the
difference in the cost of the two queries is negligible, we can choose to go for the variant that makes
it easy to track query performance over time, and I've been doing that for some years now.

It also used to be that the `in` operator was limited to 1000 elements, but I'm not sure if that's still 
the case. I do shudder to think about having 1000 copies of the same query with different numbers of 
placeholders and calls in my telemetry, though. Consider whether you can use arrays instead?


