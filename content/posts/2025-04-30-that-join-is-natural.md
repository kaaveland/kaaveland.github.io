+++
title = "That join sure is a natural"
date = "2025-04-30"
tags = ["sql", "postgres"]
+++

Working with SQL can sometimes be painful, _especially_ when you have composite keys and many tables to join. Today I want to write a helpful tip for designing data models with such keys, to make it less painful to handwrite SQL for them. 


> **_TIP:_** Introduce a consistent naming standard for all columns that take part in a primary key, so that the column has the same name in all tables it is used, also where it's on the referencing side of a foreign key.

That's it. That's the tip. Now let's talk about why this makes sense. To do that, I want to bring up a small schema I made in [the post about identifying missing indexes for foreign keys](/posts/2025-04-04-finding-missing-indexes-in-pg-catalog):

```sql
create table country(
    id bigint generated always as identity primary key,
    country_code text not null
);

create table organization(
    name text not null,
    country bigint not null,
    
    primary key(name, country),
    foreign key(country) references country(id)
);

create table account(
    country bigint not null,
    organization text not null,
    email_id bigint not null,
    name text not null,
    
    primary key(country, organization, email_id),
    foreign key(country) references country(id),
    foreign key(country, organization) references organization(country, name)
);
```

This schema does currently _not_ exhibit the naming standard I am advocating here:

- The primary key of `country` is `id`
- When used as a foreign key, it is named `country`

This means we must join like this, using the `on` clause:

```sql
select
    country_code
from country join organization on country.id = organization.country
where organization.name = 'Illuminati';
```

## Revised schema

Let's revise the schema to bring it in line with the tip, so it's easier to see what I mean:

```sql
create table country(
    country_id bigint generated always as identity primary key,
    country_code text not null
);

create table organization(
    organization_name text not null,
    country_id bigint not null,
    
    primary key(organization_name, country_id),
    foreign key(country_id) references country(country_id)
);

create table account(
    country_id bigint not null,
    organization_name text not null,
    email_id bigint not null,
    name text not null,
    
    primary key(country_id, organization_name, email_id),
    foreign key(country_id) references country(country_id),
    foreign key(country_id, organization_name) references organization(country_id, organization_name)
);
```

Now we can rewrite the previous query to this:

```sql
select
    country_code
from country natural join organization
where organization_name = 'Illuminati';
```

Here's another one that also works:
```sql
select 
    account.name
from account natural join country
where country_code = 'NO';
```

For outer joins, the syntax is:

- `natural left join`
- `natural right join`
- `natural full join`

## What sorcery is this?

[Wikipedia](https://en.wikipedia.org/wiki/Join_(SQL)#Natural_join) has this to say about natural join:

> The natural join is a special case of equi-join. Natural join (⋈) is a binary operator that is written as (R ⋈ S) where R and S are relations.[6] The result of the natural join is the set of all combinations of tuples in R and S that are equal on their common attribute names.

In less formal terms, a natural join uses the columns that have the same names on both sides of the join if their types are compatible. If you set up your foreign keys right, and match column names, it does the natural thing for you. Natural join is part of the SQL standard and should work in most RDBMS.

## Too much sorcery

If that gave you pause, I agree. I prefer to avoid `natural join` in most cases, because it feels brittle. Introducing a new column in a table can silently change all the join conditions in queries that use it. That's nightmare fuel. I think it's fine to use for ad-hoc exploration, but not in a code base where queries live and change for a long time. Here are some column names that are common and could end up doing the wrong thing for you:

- `name text`
- `description text`
- `updated_at timestamptz`
- `created_at timestamptz`

But there's a less magical shorthand that is almost as good, the `using` clause to `join`. In a join like that, you specify the column names that you want to join on, and they must exist on both sides of the join. It looks like this:

```sql
select 
    account.name
from account join country using(country_id)
where country_code = 'NO';
```

Or like this:

```sql
select
    email_id
from account 
    join organization using(country_id, organization_name)
    join country using(country_id)
where country_code = 'NO';
```

I think this strikes an excellent balance between convenience and readability. I find myself using this _a lot_ when doing any sort of analytics if the schema supports it. I'll generally start a query at the `from` clause and bring in all the tables I need, and it feels very natural to start out like this.

This is really one of those things that make sense to set up lints and rules about when starting out a new project. It's kind of annoying to retrofit this on a running system, and possibly not worth the hassle. But if you're starting something new, maybe consider it!

I maintain a tool named [eugene](https://kaveland.no/eugene) for checking SQL migrations, and I'm going to add an optional check that can help warn when a referencing column does not match the name of the referenced column.