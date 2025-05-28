+++
title = "Deploying to BunnyCDN and protecting Norway from drop bears"
date = "2025-04-20"
modified = "2025-04-21"
tags = ["cloud", "cdn", "cicd"]
+++

Not long ago, I wrote about [running containers](/posts/2025-04-14-running-containers-on-the-cheap) as part of moving my hobby projects to European cloud providers. That post was focused on running good old Linux servers. I briefly mentioned [BunnyCDN](https://bunny.net) but didn’t dive into the details. It's time to dive into the details!

## What the flark is a CDN?

A [content delivery network](https://en.wikipedia.org/wiki/Content_delivery_network) is a geographically distributed network of servers that can deliver content to your users, close to where they are. It's useful, because the speed of light isn't fast enough to make pages load quickly across the other side of the globe. Seriously, the fastest thing in the universe cannot deliver cat pictures to people quickly enough. By using a CDN, you can geographically distribute assets like cat pictures, HTML, CSS, JavaScript, video files, fonts and much more.

It turns out that most people who read my blog are located quite far from Finland, where my new server runs. Having to make one request to my page, then several others to retrieve assets would make my tiny, static blog very slow for people on the west coast of the USA or in India.

## What difference does it even make?

To test this, I used the [pingdom speed test](https://tools.pingdom.com) to check the performance from Sydney, Australia. My reasoning is that Australia is very far from Finland. Apparently it's around [13 394km](https://www.distancefromto.net/distance-from-australia-to-finland). That is 13 394 000 meters, almost the same order of magnitude as the distance light travels in one second. Light would travel this distance in about 45 milliseconds. If we could somehow use a beam of light curving around the earth from Finland to Australia to transmit a TCP packet, it would still take around 90 milliseconds for a single round trip.

Of course, we can't beam a TCP packet on a light beam. There are all sorts of obstacles in the way that makes it take a lot longer. In fact, loading the frontpage of my blog from Sydney, Australia takes around 1.35 seconds when connecting directly to my server. I think that's actually amazingly fast for the distance. There is an [incredible amount of stuff](https://danluu.com/navigate-url/) that needs to happen for this to work at all.

Pulling my page from the CDN instead, it appears to take around 100 milliseconds. That's because my site is being cached in lots of locations around the world by BunnyCDN:

{{< img src="/posts/2025-04-20-deploying-to-bunnycdn/bunny_pop_map.png" alt="A world map showing CDN data center locations, with world wide coverage." >}}

It's a pretty respectable improvement. Any page that expects a global audience would do well to put at least the static assets on a CDN. It is an easy win for performance and doesn't have to be a big investment.

Note that this does not fix low response time to my container services. If I wanted to make those fast for Australians, I would need to run a copy of my container somewhere near them. If they threaten me with some of their dangerous wildlife, I might. I wouldn't want Norway to be invaded by [drop bears](https://en.wikipedia.org/wiki/Drop_bear). For now, demand has been comfortably low...

## Is this a new problem to me? 

I used to host my page on GitHub pages, which does have a CDN. Then, when I realized I wanted to expose my page on multiple domains, I moved it to another hosting provider, which also had CDN (it was hard to do this on GitHub pages a few years back).

I didn't want to make my static pages slower for everyone when I migrated my containers, so I wasn't willing to let go of this service when I moved my containers to Hetzner. Hetzner does not provide CDN, so I had to find another provider for that.

## Why BunnyCDN?

I'm not sure what particular reason made me pick BunnyCDN from [european-alternatives.eu](https://european-alternatives.eu/category/cdn-content-delivery-network), but I liked the pricing. The self-signup was pleasant, the coverage looked great, and I found it interesting that there's a project for running containers "on the edge."

If the drop bears actually do go after me, I could easily fix it.

I've had to send a single request for support. I got an answer from a real human being in less than 30 minutes, even though I was on a free account and it was a Sunday. I've been happy with my choice.

## How does it work?

There are two main modes of operation for the CDN service that seemed relevant to me.

Point a domain at the CDN. Point the CDN at a server. The CDN acts like a cache. It will fetch resources from the server if they are not in the cache, otherwise return them directly. The nice thing about this is that you hit the ground running. This is what I did at first. I would expose my Hetzner VM as an Origin server to a BunnyCDN pull zone. The pull zone creation [guide](https://support.bunny.net/hc/en-us/articles/207790269-How-to-create-your-first-Pull-Zone) shows just how easy it is to get started with this approach.

The other approach is to use something called a Storage Zone. This is a bit more involved because you need to push files into the Storage Zone, so there are more moving pieces to set up.

The disadvantage of the first approach is that you can't just ignore that the Pull Zone is there. For a low-traffic page like mine, I want to set a high cache expiration time. Otherwise, the content people are retrieving is unlikely to be cached, and their request will end up going to the origin server anyway. The way I solved this initially was to set an absurdly long Cache Expiration Time in the pull zone, and make the pull zone turn off the browser cache entirely. Then, whenever I deployed a new blog post, I would purge the pull zone cache. Then, for a little while, everything is dog slow for everyone, until the cache is repopulated again.

There are ways of alleviating this issue. You can purge specific URLs, like RSS feeds, the index page, the archive page, the atom feed, the tag page, the... You get the drift. This felt like the wrong solution.

## Deploying with Storage Zones

Using Storage Zones for deployments sort of fixes this, because Storage Zones are geo-replicated. You upload your site to a Storage Zone, which is just like a remote file share. It is then automatically replicated to all over the world. Then you [connect](https://support.bunny.net/hc/en-us/articles/8561433879964-How-to-access-and-deliver-files-from-Bunny-Storage) a pull zone to the Storage Zone.

The pull zone will still need to fetch from the Storage Zone, but the Storage Zone is going to be a lot closer than the origin server. Australians no longer need to fetch cat pictures from Finland. They can get them from Sydney instead. Cache expiration time no longer needs to be absurdly long. The drop bears are pleased. Norway is saved.

{{< figure src="/posts/2025-04-20-deploying-to-bunnycdn/happy_dropbear.jpg" caption="A very pleased drop bear. An AI generated this. It was much too dangerous to obtain a real photograph." alt="An image showing a very pleased drop bear" >}}

## If Storage Zones are great, why wait?

When I initially started using BunnyCDN, I was moving a lot of things all at once, and I didn't want to sink too much time into something before I was sure I wanted to keep using it. I didn't want to use a web ui to upload files. There was the option to use FTP or an HTTP API.

I didn't want to try using FTP, and integrating the HTTP API into my CI seemed annoying, there didn't seem to be a builtin sync, or capability of receiving an archive with all the files. This week, I've had some time to kill, so I decided to look at it again. In the end, the only reason it was time-consuming is because I made it so.

## Thumper

I made a tool I named [thumper](https://kaveland.no/thumper/), after a very famous rabbit. It can sync a folder of files with some path within a BunnyCDN storage zone. It was an excuse to have fun writing some Rust code. I found other options after I had started making it. I was having fun, so I didn't stop.

I used the [crossbeam](https://docs.rs/crossbeam/latest/crossbeam/) crate to do concurrent file listing and file uploading. I really like this crate. Scoped, fearless concurrency with message-passing is great. I added auto-completion, check-summing, dry-runs and built documentation. I made binary releases for the major platforms (even Windows), and docker images for both arm and x86-64. It was fun and relaxing.

I made a guide for [deploying a static site](https://kaveland.no/thumper/bunnycdn.html) with BunnyCDN storage zones and GitHub workflows. This workflow is taken from the documentation for thumper:

```yaml
name: Deploy documentation

on:
  push:
    tags:
      - '*.*.*'
  workflow_dispatch: {}

jobs:
  deploy_docs:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: jdx/mise-action@v2
    - name: Render CLI help
      run: cargo test
    - name: Render mdbook
      run: mdbook build docs
    - name: Deploy docs to kaveland/thumper
      run: thumper sync docs/book kaveland --path thumper --concurrency 4 --verbose
      env:
        THUMPER_KEY: ${{ secrets.THUMPER_KEY }}
    - name: Purge pull zone
      run: thumper purge-zone 3644443
      env:
        THUMPER_API_KEY: ${{ secrets.THUMPER_API_KEY }}
```

The code is available under the MIT license over at [GitHub](https://github.com/kaaveland/thumper). The tool is easy to install with [mise](https://mise.jdx.dev/), simply `mise use ubi:kaaveland/thumper@latest`.

But you don't have to use `thumper` to deploy to a storage zone on BunnyCDN, there are options like [bunny-launcher](https://bunny-launcher.net/) and there's an official [SDK](https://bunny-launcher.net/bunny-sdk/quickstart/).

## Is this serverless?

I'm deploying my static assets directly to Storage Zones now, in case Finland decides to tariff imported cat pictures. The server's still there, but it is now only responding to API traffic and attempts to break into the WordPress installation that isn't there. I'm delighted with BunnyCDN and plan to keep my pages there for the foreseeable future. It strikes a great balance between cost, ease of use and options to expand if I get more complicated requirements later.

Thanks for reading!
