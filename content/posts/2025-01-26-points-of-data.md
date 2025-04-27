+++
title = "🎶 These points of data make a beautiful line 🎶"
date = "2025-01-31"
lastmod = "2025-04-27"
tags = ["monitoring", "OpenTelemetry"]
+++

One of my most vivid memories is from the day in my late teens when I first got
a contact lens for my left eye. It took a long time to discover that I had poor
vision on this eye, you see, like many people, I chose to keep both of my eyes
open when I wasn't sleeping. It was the headaches that sent me to a doctor. I
was adamant that I could see well, but when he blocked my right eye, I had the
humbling experience of no longer being able to read the biggest letters on the
poster. It turned out that my headaches were probably due to my brain working
overtime to interpret the world using mostly only one eye. My appointment with
an optician was only a few days later, and I got to try a contact lens that same
day.

The headaches were almost worth it for the childlike wonder I experienced
that day, when I got to see what motion actually looked like at a
distance. There's a particular tree in Mandal that I spent almost an hour just
looking at, it was a windy day, and the motion of the branches and leaves was
incredibly fascinating. I didn't know what I had been missing out on at the
time. There's a good chance that my vision on my left eye had been bad for a
very long time, or maybe it was never good to begin with.

My vision has gradually been getting worse on both eyes over the years, and so I
make sure to visit an optician regularly. Whenever I end up with a new
prescription, I take care to spend time appreciating what the world looks like,
knowing that I won't notice the day-to-day gradual decline in visual fidelity.

## Prescriptions in observability since 2013

Professionally, I don't have a lot of memories that come close to that story,
but there have been many times when I felt like I got a prescription
renewal:

- In 2013, when I first got to set up Kibana and Elasticsearch, and could
  visualize my applications to a whole new level compared with `grep` and
  `tail`. I used to sit and write clever regexes, piping `grep -o` into `sort |
  uniq -c` so I could make visualizations before this.
- In 2016, when we set up InfluxDB and Grafana at
  [Bring](https://developer.bring.com/blog/metrics-at-mybring/) and started
  _really_ caring about measuring things. This very much felt like the start of
  something great, and [this culture still
  lives](https://www.tek.no/nyheter/nyhet/i/mQOrqp/her-er-postens-hemmelige-rom).
- In 2023/2024, when we set up Grafana, Loki, Tempo, Prometheus and
  OpenTelemetry at [Sikt](https://sikt.no/) and I realized how _easy it is_ to
  measure things now, how much of the work that someone else has already done
  for you.
- In 2025 at Sikt, when we enabled our telemetry stack for a bunch of
  applications where we had been only using logs before, all at once. Suddenly
  we could see clearly.

It occurs to me that if I hadn't been paying attention to these things for many
years now, just relying on logs, then been exposed to auto-instrumentation
with OpenTelemetry in 2025, I might get an experience close to the day when I
got contact lenses the first time, and that's why the story is relevant.

If you're not using tools like these now, there are valuable facts in your world
that are deeply hidden from you. It's easier than ever to start using them, and
you should. This post is the introduction to a series that will help you get
started using OpenTelemetry aiming to cover a few different stacks, as well as
one possible observability stack to use, and some examples of what that enables:

- The JVM in general
- next.js and node.js
- cats-effects and zio
- The opentelemetry collector
- The grafana-stack, with tempo, loki and prometheus


## Not convinced yet?

I realize that the two previous sections could look a lot like I'm trying to
capitalize on [FOMO](https://en.wikipedia.org/wiki/Fear_of_missing_out), but I'm
not selling anything, so please hear me out.

[OpenTelemetry](https://opentelemetry.io/community/mission/) is a
community-driven initiative to standardize and specify protocols, APIs and
semantics of observability data. All of the work is open, and anyone can
implement the specifications. Someone probably implemented them for whatever
tools you're using in the telemetry space already. You wouldn't bind yourself to
any vendor or product by choosing to try it, in fact, it would make it very easy
to try multiple and choose based on experience. That's one great thing about
choosing open standards and specifications. Another one is that a lot of
libraries now instrument their code with OpenTelemetry, so you don't have to do
it yourself.

Back in 2016 when I worked at Bring, we started taking metrics pretty
seriously and [blogged
many](https://developer.bring.com/blog/tuning-postgres-connection-pools/)
[times](https://developer.bring.com/blog/measuring-jvm-stats/)
[about](https://developer.bring.com/blog/forecasted-alerts-with-grafana-and-influxdb/)
[stuff](https://developer.bring.com/blog/b-scripts/) we did to get metrics. You
can get this kind of data with almost no work now, and because the names, labels
and values are now standardized, you can make dashboards that will work across a
ton of different applications and runtimes. Back when I started getting
passionate about metrics, we had to take care to set things up in alignment
ourselves, and a lot of the time we needed several attempts to design the right
sets of labels. I'm saying this, because this is work that is no longer
necessary to undertake yourself in order to get things like:

- Duration metrics of all http calls made by all your applications labeled by
  the status codes and host names they were trying to reach.
- Duration metrics of all http calls made to your applications labeled by the
  status codes they resulted in and their http route.
- Connection pool usage in your applications.
- Correlation ids propagating all the way from the client into all of the
  backends that process the requests, transitively.

## Business value of telemetry

All of that stuff is great to have for operational stuff, debugging incidents
that happen and solving bugs. It's an amazing place to start where you get a ton
of things for very little effort. But we're still just dipping into the surface
of what we can do when we get comfortable using these tools. The most valuable
things happen when we find some telemetry that aligns really well with business
value. It could be a conversion rate, a time to convert, amount of orders
processed or something else entirely. When we find something like this, we can
monitor it and use it to pick up symptoms of unforeseen problems, things that
are really hard to uncover without real users stressing the whole system.

If you roll out a new version, and the conversion rate immediately drops, you
know there's a problem. You get to roll back before any damage is done, before
identifying whether the problem was due to some CSS change moving around
buttons, a fresh validation error, a logic bug, a changed price calculation or
something else entirely. People will often tell you [that finding bugs earlier
in the
lifecycle](https://buttondown.com/hillelwayne/archive/i-ing-hate-science/) is up
to a 100 times cheaper than in production. At the same time, it is also true
that we can't all afford the level of QA required to end up with 0 defects. You
may well be at a level of QA where it is cheaper to optimize for fast detection
of bugs and fast recovery time, than increasing the spend on QA. Investing a
little bit in telemetry can go a long way in identifying problems before there's
an outage.

There are tons of other reasons to measure things. How many clients use this
endpoint, what coordination is necessary in order to get rid of it? Can we
develop a shitty first version of a feature and measure adoption before we
refine it? There's an incredible amount of use-cases and the culture for finding
them will come as people adopt the tools and see the value. I think
OpenTelemetry delivers enough of the good stuff that people will want to learn
more. It isn't perfect, we're talking about standards and specifications after
all. There are plenty of warts to get annoyed at, but all of that stuff is
far outweighed by how useful the good parts are. Adoption has been heading the
right way for a long time already, and it's only going to get more widespread
from here.


## Next part

The next part of this blog is a collaboration with a colleague from work, and is available [here](https://arktekk.no/blogs/2025_otel_part_2_agent).