title: How to buy the right fishing license
category: data science, fishing, python
date: 2023-06-11
modified: 2023-06-11
status: Draft

For some years now, I've been building machine learning models to help me
select fishing licenses any time they cost more than a few hundred NOK. It's
quick and easy, I enjoy it is, it is very effective. The next section provides
my motivation for doing all this extra work instead of just buying a license
going by recommendations and rumour, feel free to skip that if you don't feel
like using machine learning needs motivation and don't like prose.

An expensive trip with nothing to show for it
--

As a kid, my younger brother and I were lucky enough to be taken on many fishing
trips to the beautiful Mandalselva river, and though we didn't always reel in big
catches, we treasured the experience of being together on the banks as we fished
beautiful, flowing rapids. As we grew older, I lost touch with fishing, but my
brother developed a love for reeling in salmon and it turned into a true passion
for him.

After several years without fishing, I decided to pick up my old hobby to
explore the woodlands around Oslo and the mountains near Rondane with a fishing
pole. Eventually, I moved to Trondheim and gifted my brother with a promise of a
week-long salmon fishing trip to take place in the summer of 2018, in my area.
My plan was to make him fall in love with the area so he would come visit often,
since I knew the salmon fishing was great in many rivers around Trondheim.

So, I started doing my research - I had to figure out where we could fish, what
the costs would look like, and where we could find the best spots. Gaula river
in the scenic Gauldalen valley seemed like the best bet, so I bought our
licenses, acting on the recommendations of a local sports shop. The day my
brother arrived, it turned out that the summer drought had turned the once
mighty river into little more than a creek.

We still went fishing, exploring the area where our fishing licenses were valid.
It was really difficult to be able to efficiently fish the
river with so little water in it, and while we had a good time together in the
sunny weather and idyllic scenery with water clear as glass, there was never
really any hope of catching salmon. On the second day, the river owner
association closed the entire river for fishing, afraid that fishing
would do lasting damage to the salmon tribe. My brother was heartbroken, and as
the elder brother, I couldn't help but try to fix the situation.

I called a relative of my wife who had a cabin in the Namdalen area, close to the
mighty Namsen river. It was a long shot, but I asked if we could borrow it for
a few days to try our luck with the fishing. Thankfully, she was more than happy
to oblige, and couldn't wait to hear how our trip went.

Excited at the prospect of trying a new river, we packed our gear and hit the
road, driving north from Trondheim towards Namdalen. On the way, we heard back
from the family friend who had put us in touch with a local farmer who had salmon
fishing licenses for Namsen. He had some last-minute cancellations due to a
forecasted flood, but we didn't know about that at the time. We just knew that
Namsen wasn't affected by the drought in the same way as Gaula.

As we drove towards Namdalen, the sun gave way to heavy rain and the skies
darkened, but we felt a sense of relief. We knew that this rain would mean
higher water levels for the Namsen river, and our chances of catching salmon
would be much better. Despite the weather, we felt optimistic and excited for
the next few days of fishing ahead. As we settled into the cozy cabin late
in the night, we felt the anticipation build for what the next few days
might bring, reveling in the knowledge that we were finally in the right place
at the right time. The rain outside only made us more aware of the beautiful
nature surrounding us, setting the stage for what would be an
unforgettable fishing trip.

The next morning, we headed to the river bank near the farmer's farm to meet him
and get our licenses. The rain was still coming down in torrents, and the river
was visibly larger than the day before. The farmer greeted us warmly at the river
bank, and told us about the forecasted flood. He offered to cancel our licenses
and let us save the money, as he didn't believe we'd be able to catch any fish
in the conditions that were forecasted for the next few days. We were determined
to fish no matter what and purchased the licenses anyway. We got a tour of the
river banks and lots of helpful tips about good spots to try at different water
levels.

Over the next few days, we fished almost every waking hour, as the swelling river
pushed us further and further out into the woods next to it, as it swallowed the
river bank completely. We observed huge pine trees and dead animals disappearing
into massive whirlpools as nature displayed the force of such a large flow over
water in an inimidating way. We caught and released a few trout and my brother
lost a salmon near the shore, and the fishing trip ended with us being wet to the
bone, having no catch to show for it. While driving my brother to the airpart, I
determined to never spend so much money and energy on something again for no
results. While driving home to my own house, I kept thinking that there must be
a way to use data analytically to buy the right fishing licenses, knowing that
Norway keeps catch statistics and water level measurements are available.

What data is available
--

In Norway, we have strict laws requiring all salmon caught in rivers to be
reported to the government for administrative purposes. This government
aggregates this information to help them understand whether the salmon tribes
are healthy, but for most rivers I know about, it is easy to get hold of the
raw catch data online. For Gaula, Namsen and Orkla, I have raw data for many
years of catch statistics that I retrieved from lakseboersen.no while it was
still used. Nowadays, it looks like [elveguiden](https://elveguiden.no/no/laksebors)
provides this data for those rivers. For Mandalselva, I scrape the html pages of
[scanatura](https://laksebors.inatur.no/bors/1542).

Any experienced salmon fisher will tell you that some places become hopeless
to fish at certain waterlevels, or early in the season, or late in the season.
For Gaula, for example, fish is often unable to make it past the powerful
Gaulfoss rapids early in the season, when the water is cold and affects the
metabolism of the fish. So the common sense of salmon fishers would suggest
that water level, water temperature and whether it's late or early in the season
are important data.

The Norwegian Water Resource and Energy Directorate provide
[hydapi](https://hydapi.nve.no/UserDocumentation/), an HTTP api that lets us
retrieve water discharge, water temperature and all sorts of other data from
measuring stations scattered throughout the country. It is free to use and
well documented.

The weather forecast can be a useful resource to try to predict whether the
water levels or temperature are about to change.
[frost](https://frost.met.no/index.html) is the API solution for accessing
historical weather records from the Norwegian weather institute and we can
use those data, shifted in time a little bit, to simulate the weather forecast
if we should want to use it for our model.
