+++
title = "Batch operations using composite keys in postgres over jdbc"
date = 2024-08-30T00:00:00Z
draft = false
tags = ["jdbc", "java", "scala", "postgres"]
+++

Throughout a career as a software developer, you encounter many patterns. Some appear just often
enough to remember that they exist, but you still need to look them up every time. I've discovered
that writing things down helps me remember them more easily. This particular pattern is very useful
for my current project. So, it's time to write it down and hopefully commit it to memory properly
this time. Although this post is specific to PostgreSQL, I'm sure other databases have the necessary
features to achieve the same results efficiently.

In my current project, we have a lot of database tables with composite primary keys. Or in plain english, we
have a bunch of tables where the primary key actually consists of more than one column. This is because a 
design principle for the database was to prefer natural keys over synthetic keys. While this is a good
design principle, it does come with some mechanically annoying consequences. The topic for this post is
the case where you have a bunch of keys in memory and need to instruct the database to delete all the 
corresponding rows. This is a fairly common kind of use case in web development, just think of all the list
views you've seen with check boxes for deleting. With a primary key that is a single column, we can just
fire off a prepared statement like this:

```sql
delete from orders where id = ANY(:ids);
```

Then we just make sure to pass `ids` as a JDBC array type, and we get efficient bulk deletes. But this doesn't
work when the primary key is composite. What we would like to do, is to express something a lot like the following
(illegal) SQL:

```sql
delete from orders where (customer_id, order_id) = ANY(:customers_and_orders);
```

And then pass in `customers_and_orders` as a JDBC array of tuples. Last time I tried this, it wasn't easily possible
to create such a value using JDBC. Fortunately there's still a way to do this efficiently, and it relies on a builtin
function in postgres that is named [unnest](https://www.postgresql.org/docs/current/functions-array.html). The
`unnest` function takes an array and returns a set of rows, one for each element. We can use it to construct a 
table value from a tuple of arrays. So suppose we have two arrays (just imagine we're passing them in over JDBC for now):

```sql
postgres=# select '{1, 2, 3, 4}' :: int[];
   int4    
-----------
 {1,2,3,4}
(1 row)
postgres=# select '{one, two, three, four}' :: text[];
         text         
----------------------
 {one,two,three,four}
```

We can use unnest to turn them into a table like this:

```sql
postgres=# select 
  unnest('{1, 2, 3, 4}' :: int[]) as order_id, 
  unnest('{one, two, three, four}' :: text[]) as customer_id;
 order_id | customer_id 
----------+-------------
        1 | one
        2 | two
        3 | three
        4 | four
```

Now we can easily use a subselect to delete the rows we want to target:

```sql
postgres=# insert into orders(order_id, customer_id) values (1, 'one'), (2, 'two');
INSERT 0 2
postgres=# delete from orders where (order_id, customer_id) = any(
  select unnest('{1, 2, 3, 4}' :: int[]), unnest('{one, two, three, four}' :: text[]));
DELETE 2
```

It is easy enough to pass two JDBC arrays of primitives, so this gets us to something that works. Note that if we
want to do filtering using columns that aren't part of a primary key, it's important to remember that SQL has 
weird rules around `NULL`. Notably, if you compare anything to `NULL`, the result is `NULL` too, and this can
come out weirdly in some cases with arrays, where you can also have `NULL` on two levels:

```sql
postgres=# select unnest(NULL :: text[]), unnest('{1, 2, 3, 4}' :: int[]);
 unnest | unnest 
--------+--------
        |      1
        |      2
        |      3
        |      4
(4 rows)

postgres=# select unnest('{one, two, three, NULL}' :: text[]), unnest('{1, 2, 3, 4}' :: int[]);
 unnest | unnest 
--------+--------
 one    |      1
 two    |      2
 three  |      3
        |      4
(4 rows)
```

With columns that are part of a primary key, it should be safe, as long as the array value that we pass in isn't `NULL`,
because postgres will automatically promote columns to `NOT NULL` if they become part of a primary key, and prevent
us from altering them back to `NULL`.

Obviously this hack gets annoying if there are a lot of tables with composite keys that contain a lot of columns, and
in such cases it may be worth adding a synthetic key to the table, just to make it more ergonomic to work with.

## Putting it all together

Here's a self-contained [scala-cli](https://scala-cli.virtuslab.org/) script that shows how to do this from the
JDBC-side. It won't look too different in Java or Kotlin.

```scala
//> using scala "3.5.0"
//> using dep "org.postgresql:postgresql:42.7.4"

import java.sql.DriverManager

@main def run(): Unit = {
  val url = "jdbc:postgresql://localhost:5432/postgres"
  val connection = DriverManager.getConnection(url, "postgres", "postgres")
  val sql = "delete from orders where (order_id, customer_id) = ANY(" +
    "select unnest(? :: int[]), unnest(? :: text[]))";
  val statement = connection.prepareStatement(sql)
  statement.setObject(1, Array(1, 2, 3))
  statement.setObject(2, Array("one", "two", "three"))
  println(statement.executeUpdate())
}
```

If you don't want to spend the storage space in your brain for this kind of pattern, my friend Øyvind has implemented
an excellent code generator for this kind of thing in his [typo](https://oyvindberg.github.io/typo/docs/) library. It
takes care of some other annoyances with composite keys as well, like generating tedious joins, and mapping to/from
the database for you. Currently it generates Scala code, but I know that there's secret plans to make it generate
Kotlin and Java as well. I highly recommend taking a look, especially if you're working with a lot of tables with
composite keys.
