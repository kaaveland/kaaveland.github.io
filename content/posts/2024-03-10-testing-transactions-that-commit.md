+++
title = "Isolating integration tests that commit transactions"
tags = ["postgres"]
date = "2024-03-10"
modified = "2024-03-10"
+++

For tests that need to touch the database, it is generally a really good idea to
roll back transactions. That way, you can run lots of tests in parallell or in
any arbitrary order and the tests won't interfere with each other. But
sometimes, that just isn't possible. One reason for this could be that the code
base handles transactions in a way that makes it really hard to get a handle on
them in the right place, or it could be a legacy code base where everything is
running with auto-commit or some other explanation. Either way, it is very
important to be able to isolate effectful tests from each other both to get good
performance out of building on multi-core machines and to avoid flaky tests or
tests that break when they run in a different order.

If your project is running postgres, there's a pretty efficient way of setting
up this test isolation even if your tests commit data. It does require that your
test harness must run as a user that has permissions to create databases, but
is otherwise a pretty simple idea. In postgres, the `CREATE DATABASE` statement
actually always creates a copy of an existing database. Normally this is
`template1`, which is set up for you when you initialize the database cluster.
But creating it from a different source is very simple:

```sql
CREATE DATABASE "$uuid" TEMPLATE "my_application_db";
```

This creates a database named `"$uuid"` that contains the same schemas, tables,
and data as `"my_application_db"`. There are some limitations to be aware of,
though. Note that this does not copy `GRANT`s from `"my_application_db"`
to `"$uuid"`, so you may need some extra steps to grant your test code
sufficient permissions on `"$uuid"` afterwards. You also can't
run this `CREATE DATABASE` statement if any client is connected to
`"my_application_db"`. Creating a database from a template is very efficient for
small databases, on the order of perhaps tens of milliseconds. So every single
test case can easily have some sort of before-test that sets up a dedicated
database only for that test-case, and then some sort of after-test that deletes
it later. It is also easy to just not run the `"DROP DATABASE "$uuid";` step if
the test should fail for some reason, so that it's possible to investigate the
database test and perhaps figure out why the test failed.

For more information about template databases, take a look at
[the documentation](https://www.postgresql.org/docs/current/manage-ag-templatedbs.html).
