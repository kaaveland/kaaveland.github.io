+++
title = "Building documentation for Eugene"
tags = ["eugene", "writing", "rust", "documentation"]
date = "2024-05-20"
+++

I've been busy working on a [documentation site for eugene](https://kaveland.no/eugene), and I
think it's starting to look pretty good. I wanted to write down some of
my thoughts around the process so far, and some of the things I've learned.

It's just been a few days since I ported my blog to hugo, so since I was
already feeling like I was up to speed on that, I decided I'd try using it
for the eugene documentation too. I experimented with a few different
setups around the [hugo-book](https://themes.gohugo.io/themes/hugo-book/)
theme, but it ended up feeling like I was having to configure a bit
too much for my taste. I think it looked really nice, but the setup
felt a bit janky and complicated, with having the submodules and 
everything in the eugene repo itself. I think my problem here is
just that doing this with hugo would require me to learn more about
hugo than I'm ready for right now.

Fortunately, it was very easy to try my hands at [mdBook](https://github.com/rust-lang/mdBook),
since I had most of the structure I needed in place after trying hugo. I 
spent less than an hour getting things working again, and now I've spent
a few more hours writing content and content generators, and it's really
starting to feel natural to work with. Fortunately for me, mdBook has
taken almost all the decisions for me, and I can just focus on writing.
There's definitely stuff you can do with hugo that mdBook just can't do,
but I don't anticipate needing any of that for the eugene documentation.

My favorite section so far is the 
[Hint reference](https://kaveland.no/eugene/hints), where each rule
that eugene knows about has its own page, with an example and a fix,
and I thought I'd write a bit about the weird and hacky way it's 
generated and how I'm going to make sure it's updated. In this post
I'll share some details about how it's set up and how I feel about it
now that I've been using it for a while.

## Build setup

Each time I add a new rule to eugene, I start by adding data about it
to [hint_data.rs](https://github.com/kaaveland/eugene/blob/main/src/hint_data.rs).
The name is subject to change, of course, but there's going to be a static data
file like that for a long time. There's a `pub const ALL: &[HintData]` that
contains all the static data for all the rules. Both the linter and the tracer
refer to this data when defining the logic for when to trigger a rule.

Once the static data is added here, there's a test that will start failing
in `render_lint_examples.rs`. This test asserts that each rule in `hint_data::ALL`
has a corresponding example at `examples/{id}/bad`. This example should
be a directory with `.sql` files that cause the rule to trigger. Optionally,
`examples/{id}/good` can show a workaround. I don't know of workarounds
for all the rules currently, but I prefer to show one when I can.

## Generating the hint pages

A requirement I had already set myself was to have snapshot tests
of each rule, so I could stay on top of formatting changes. The
snapshot tests were already generating markdown report files that 
were suitable to add to the documentation as examples, but I wanted
to add some context for those reports. To me, the snapshot test
idea felt like exactly the right place to generate the hint pages
for the documentation. That way, I make sure to not accidentally
change anything. By checking in the results, I also make sure that
the documentation is diffed and reviewed in pull requests before
updating the webpage.

I've added [handlebars](https://docs.rs/handlebars/latest/handlebars/)
templates for the tool itself, and now also use that for generating 
some of the content for the documentation. I chose handlebars because
it's what mdBook uses and I thought I might have to do custom templates
for mdBook at some point. [Tera](https://keats.github.io/tera/docs/)
honestly looks more like what I'm used to, but it turns out I care
surprisingly little about choice of templating language. I prefer not
to do anything complicated with templates anyway. :shrug:

One thing that _is_ a bit hacky is the way I make sure that mdBook
learns about these pages. For mdBook to render markdown to html,
the markdown file has to be in the `src/SUMMARY.md` table of contents
somewhere. Since I was already on a roll with the snapshot tests,
I decided to just add a test that generates the table of contents too.

## Drawbacks

The local development experience could be nicer. Instead of invoking
`mdbook serve docs` and forgetting about it, I need to rerun 
`cargo test` when I am working on the templated things. I can live 
with this fairly easily, but I do forget to do it sometimes.

There's also the fact that the docs that get deployed to the website
are the docs that are checked in. The github workflow does not
install rust and run the tests, so it's happened once or twice that
I've pushed a change to the way the docs are generated, but 
forgotten to run `cargo test` locally to generate the docs first.
I don't really think this is a big problem, but if it keeps
happening I may have to do something about it.

## Learning points

I still really like hugo! :raised_hands: It's a great tool for a blog, but I think
mdBook is a better fit for the eugene documentation. I plan to add
some rust code examples to the documentation, and I think it's very
cool that mdBook can run and test the code examples for me. mdBook
is simple in exactly the right way for my :brain: so it's been a perfect
fit so far.

Adding a template engine was an important upgrade to the eugene codebase. :raised_hands:
To be fair, this is no surprise. I think it was the right time to do it,
in the exploratory phase of the project, I didn't want to get bogged down
in researching the options and having to make choices about dependencies.
I think doing it badly at first, then doing it right if it turns out to be
valuable is often a good strategy. This would make an excellent subject
for another blog post, so I'll try to revisit that idea in the future.

I've asked for some advice from colleagues on how to structure the
documentation and I all the suggestions I've got have been very useful.
I haven't implemented everything yet, because it'll take some time. I'm
very fortunate to work together with enthusiastic and knowledgeable
people who don't mind sharing their thoughts with me.

I've relearned that I really like making information accessible! If
I'm going to succeed in helping people write safer schema migrations,
I think having good-looking documentation is essential. :raised_hands:

## Future work on eugene

I've added a bunch of new issues to the eugene repo. Some of those are
going to be feeling like a slog to work through. I've decided to unify
the "hint" and "lint" terminology and use the word "rule" from now on.
This impacts practically every file in the codebase, both documentation
and code. I think it's important to do this because I want to be 
consistent and clear.

I also want to make `eugene lint` and `eugene trace` able to eat
multiple `.sql` files as input, or possibly even a folder. A lot of
the current snapshot tests deal with stuff that would be natural to
handle as a feature like this.

I haven't added a ticket for the most fun idea I currently have,
which is to build a small web app with a text input field, so
people can play around with `eugene lint` in the browser. In
the spirit of learning the most about Rust from this project, that's
probably very valuable for me to do, and I think it's something that
could help me find users for the tool. I suspect that having to use
`cargo install` is a bit of a barrier for some people, and I'm not
ready to set up any sort of package distribution for it yet.
