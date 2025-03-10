+++
title = "What if that isn't a bool?"
date = "2025-01-08"
modified = "2025-01-08"
tags = ["programming", "code"]
+++

A common way that code grows difficult to reason about is increasing the number
of things you must keep in your head simultaneously to understand it. Often,
this simply happens by adding one attribute, one variable, one column at a
time. Some people are gifted with a great capacity for working memory, but most
of us aren't -- having to hold the state of 5 variables in your head
simultaneously to understand a piece of code may be pushing it far, according to
[this](https://en.wikipedia.org/wiki/Working_memory) article from wikipedia:

> Working memory is widely acknowledged as having limited capacity. An early
> quantification of the capacity limit associated with short-term memory was the
> "magical number seven" suggested by Miller in 1956.[20] Miller claimed that
> the information-processing capacity of young adults is around seven elements,
> referred to as "chunks", regardless of whether the elements are digits,
> letters, words, or other units. Later research revealed this number depends on
> the category of chunks used (e.g., span may be around seven for digits, six
> for letters, and five for words), and even on features of the chunks within a
> category.

A common pattern that pushes _my_ working memory, is when I'm looking at an
entity, or some database row, where there are lots of booleans being used to
make decisions in code. Here are some examples of names that I think are common
for these kinds of things: `is_canceled`, `is_draft`, `is_published`, `is_paid`,
`is_approved`, `is_done`, `is_withdrawn`. These also come with variants like
`canceled_at`, `published_at`, `approved_at` and so on, where the boolean is
implicitly derived from the presence of a timestamp.

Alone, each of these things all added a tiny amount of complexity, of new
behaviour, but together, they may create massive truth tables that make it
difficult to get validation code correct when adding the next. You may get code
that is deeply nested or you may look at different variations of [de
Morgan's laws](https://en.wikipedia.org/wiki/De_Morgan%27s_laws) to check if you
can simplify difficult conditions.

At least some of the time, the correct reaction to this is to take a step back,
and ponder: Is that really a `boolean`? Maybe you don't need
`Article` to own `is_draft`, `is_published`, `is_withdrawn` booleans at all?
Perhaps, what you're looking at is a `State` of some sort. Perhaps the `state`
of `Article` can be `draft`, `published` and `withdrawn`? One nice thing about
this kind of thinking is that it can often make heaps of nonsense states
unrepresentable in the database without relying on lots of check-constraints,
and if you really need the booleans for some reason, you can derive them.

Maybe `Article` isn't even a thing that owns a `State` that can be `draft`. What
if `Draft` and `Article` are separate things entirely, and `Article` is what
becomes of a `Draft` that you `publish()`? This may help you develop a better
language for talking about important domain objects. It might also let you use
the type system prove the absence of some kinds of bugs: Perhaps you can't
`cancel()` a `ShoppingCart()` or `empty()` an `Order`.

When modeling the database, it could be that that it makes the most sense to let
your columns stay timestamps or booleans, maybe it's a really rough job to
refactor it. On the other hand, maybe you have some kind of complicated trigger
logic to keep a history table. Maybe it would help to have some kind of primary
table for the entity, and a secondary table for state transitions:

``` sql
create table article(
    id bigint generated by default as identity primary key
    -- ...
);

create table article_state(
    id bigint generated by default as identity primary key,
    article bigint not null references article(id),
    state_changed_at timestamp with time zone default now(),
    state text not null check (state = ANY('{draft, published, withdrawn}'))
    -- ...
);

```

Now it is easy to get an article together with its latest state:

``` sql
select distinct on(state.article) state
from article a join article_state state on a.id = state.article
order by state.article, state.id desc limit 1;
```

Or the entire history of states:

``` sql
select
  state.state,
  state.state_changed_at as state_start,
  lead(state.state_changed_at)
    over (partition by article order by state.id) as state_end
from article a
  join article_state state on a.id = state.article
where a.id = 1;
   state   |          state_start          |             state_end
-----------+-------------------------------+-------------------------------
 draft     | 2025-01-08 21:58:51.170734+01 | 2025-01-08 22:03:58.995427+01
 published | 2025-01-08 22:03:58.995427+01 | 2025-01-08 22:09:07.225505+01
 withdrawn | 2025-01-08 22:09:07.225505+01 |
(3 rows)
```

There are lots of times when adding that boolean or timestamp is the right way
to go. But there are also lots of good reasons to ask yourself the question:
"What if that isn't a bool?" I'll be thankful the next time I can add a state
transition to the code base instead of trying to create neat and structured code
around 2^5 possible states of booleans. To quote [von
Neumann](https://en.wikipedia.org/wiki/Von_Neumann%27s_elephant), there's a lot
of complexity in 5 parameters:

> With four parameters I can fit an elephant, and with five I can make him
> wiggle his trunk.
