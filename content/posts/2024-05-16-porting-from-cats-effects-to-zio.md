+++
title = "Porting an application from cats effects to ZIO"
tags = ["scala", "zio", "cats-effect"]
date = "2024-05-16"
date-modified = "2024-05-16"
+++

In my current project, we're working on a large-ish code base that is written in
Scala and uses [cats effect](https://typelevel.org/cats-effect/) as an effect
system in large parts of the code base. If you're not familiar with what an
effect system is, I think the most important detail is that it's a tool that
gives you certain superpowers if you promise to be honest about it when your
code does things that can be considered "effectful", such as interacting with
the network or reading files. We use the `IO` monad from cats effect, which is a
wonderful way of writing async, concurrent code that looks a lot like
synchronous code.

This is the first project where I've been using an effect system in Scala, and
it's been a fascinating experience. Something that I think is kind of
challenging in our case is that we've inherited a code base where a lot of
code is dishonest about being effectful -- that's to say, it simply existed before
the rest of the code started using an effect system. Many of the libraries
that we use do not integrate with our `IO` monad and use exceptions to handle
errors, so there's actually quite a lot of this code. Previously I've only worked with
`IO` in Haskell, where using it isn't optional so this kind of challenge has been
new to me and I don't really have a good idea about how to handle it.

On the whole, I feel very happy about working with cats effects, but I do think
that there's an issue with this kind of ecosystem where it's hard to gradually
adopt it.

Despite our happiness with cats effects, we've ended up having to look at and
consider [ZIO](https://zio.dev/) for some of the things we do. Namely, we've
been instructed to offer GraphQL APIs and after testing a few options, we decided
that [caliban](https://ghostdogpr.github.io/caliban/) looks like the best option
for us. It integrates really nicely with ZIO, and specifically ZQuery, which is
a very cool library that makes it easier to batch and cache GraphQL queries
efficiently. There's a cool [paper](http://simonmar.github.io/bib/papers/haxl-icfp14.pdf)
you can read about Haxl, which inspired ZQuery, although I have to warn that
the paper isn't light reading.

A theory we had early on, is that it would be simpler for developers to work
with only one effect system in the code base, and so if we needed to have ZIO
anyway, we should consider porting the rest of the code base away from cats effects.
This is something we decided to timebox and make an attempt at, and I thought it
might be interesting to share some of the things we've learned in the process.

## Devising a method to refactor

There are a **a lot** of common signatures between `IO` and `ZIO`, and we had
strong reasons to believe that in many places, just changing the type would be
enough. The first thing we did was to define an `IO` alias for `ZIO`, so that
we could update the effect type we used across the whole code base by only editing
import statements:

```scala
type IO[+A] = zio.Task[A]
```

Replacing all imports `cats.effect.IO` with our `IO` alias was simple to do with
simple search and replace, and some manual touch up for the most complex imports.

After doing this, there was a fairly limited number of patterns we had to update,
and some of them, we could fix by adding extension methods to our `IO` alias. Here's
a non-exhaustive list of things we needed to change:

- `IO.raiseError` became `ZIO.fail`
- `IO.pure` became `ZIO.succeed`
- `IO.attempt` became `ZIO.either`
- `IO.apply | IO.delay` became `ZIO.attemptBlocking`
- `IOApp` became `ZIOAppDefault`
- We had to import `import zio.interop.catz.*` all over the place for `EitherT` and
  things like that to work.

On the whole, this stuff wasn't so bad and took me the better part of a day to fix
in the whole code base (which is maybe 150k lines?) by simply hitting compile and
fixing the next error, one after another. It was boring, but not very hard.

Once that was done, I very quickly had a code base that compiled, and almost all
the tests immediately passed. Most of the few test failures were easy to fix and
were simple things like wrong translation of `IO` methods to `ZIO` methods.

## The actual hard part

There was one test failure that bothered me. In particular, the test was doing an
actual call to a [http4s](https://http4s.org/) service, and it was expecting to
have some error handling done, but it simply wasn't happening. It looked like our
error handling was simply being ignored by `ZIO`, and I had a hard time figuring
out why.

This honestly took me a few hours to figure out and I only realized what
was wrong completely by accident. At some point I randomly remembered reading
documentation about cats effects 2 that mentioned something about expecting only
pure functions to be provided to `map` and `flatMap`. I decided to look up
[this section](https://typelevel.org/cats-effect/docs/2.x/datatypes/io#use-pure-functions-in-map--flatmap)
and see why my brain thought it might be relevant.

> When using map or flatMap it is not recommended to pass a side effectful function,
> as mapping functions should also be pure.
> [...]
> Note that as far as the actual behavior of IO is concerned, something like
> `IO.pure(x).map(f)` is equivalent with `IO(f(x))` and `IO.pure(x).flatMap(f)` is
> equivalent with `IO.defer(f(x))`.
>
> But you should not rely on this behavior, because it is NOT described by the
> laws required by the `Sync` type class and those laws are the only guarantees
> of behavior that you get. For example the above equivalence might be broken
> in the future in regards to error handling. So this behavior is currently
> there for safety reasons, but you should regard it as an implementation
> detail that could change in the future.

I quickly realized that due to our code base having a lot of dishonest code that
pretended to be pure, but wasn't, we had a lot of places where we were passing
side effectful functions to `map` and `flatMap`. cats effects is saying it can
handle that (and that we should feel bad about doing it!), but how about ZIO?

An interesting difference between `ZIO` and `IO` is that `ZIO` has an error
channel in the type, and we'll often see a signature like `ZIO[Env, Throwable, A]`.
`ZIO` can also represent an "infallible" value, that is, something that can't
possibly fail: `ZIO[Env, Nothing, A]`. A value like that has to always contain
an `A`, and could never contain an exception. If `ZIO.flatMap` were to allow
functions that could throw exceptions, it would have to always return some variant
like `ZIO[Env, Throwable, A]`, which means you couldn't compose `ZIO[Env, Nothing, A]`
at all. So how does `ZIO` handle this?

So it turns out that this is what's called a
[defect](https://zio.dev/reference/error-management/types/defects/) in `ZIO`. This
is for unexpected and unrecoverable errors, like a throwing an `Exception` in `map` or
`flatMap`. You can move such defects to the error channel of the `ZIO` monad by using
`.catchSomeDefect`, like this:

```scala
// some dishonest code that says it can't fail
val infallible: ZIO[Any, Nothing, String] = ???
val fallible: ZIO[Any, Throwable, String] = infallible.catchSomeDefect {
  case e: JsonParseException => ZIO.fail(e)
}
```

Doing this operation at the top level of our http4s service made the test pass
and for a moment, I was happy to see that we were able to refactor the entire code
base in only a few days. But then I started having doubts.

There's a lot of error handling code in a 150k line code base. There's an impossibly
large amount of calls to `.map` and `.flatMap`. How could we possibly verify that
we've installed all the necessary `.catchSomeDefect` calls in the right places? How
could we possibly hope to verify that we've done this correctly? I started to feel
a bit of despair and realized I that this decision was too big to make without
consulting others.

## Opting for the safer route

After discussing this with the teams that share this code base, we decided that it
was hard to accept this risk. The task of refactoring to use `ZIO` was something we had
speculatively decided to be a good idea, but it was unclear to us what we would risk by
_not_ doing it. It seemed pretty clear that we would have to take a risk that was hard to
quantify, in order to proceed with the refactoring, and for very uncertain benefits, it
seemed best to let this one go. This is one of the cases where I think timeboxing is very
valuable, in the end, this task did not cost us much time, and we learned a lot from it.
It's hard to say for sure, but I suspect that if we had sunk more cost into this, it
would've been harder to stop.

At this point we have both effect systems in use in our code base, and so far it seems
to be working out fine. It also turns out that we're taking the GraphQL part of the code
out of the main code base and developing it in a separate repository, so we don't have
to worry about mixing the two effect systems in the same code base, so it may have all
worked out for the best.

## Some lessons learned

- Time boxing is very valuable, and it is fun to work against the clock. ⏰
- Doing a lot of work in a short time, then throwing it away is fine! 🗑️
- Conducting experiments is sometimes the best way to make sure that decisions are
  well-founded. ✅
- But often, there's no right or wrong choice anyway, just different degrees of risk. 🎲
- There's a significant and big difference in the way that exceptions in `.map` and
  `.flatMap` are handled between `IO` and `ZIO`. 🤔
- It seems like gradually adopting an effect system is very hard, fraught with perils
  and probably not worth it in most cases. 🤔
