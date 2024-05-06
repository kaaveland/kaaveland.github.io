title: Friends don't let friends export to CSV
tags: data
category: data
date: 2024-03-24
modified: 2024-04-04

I worked for a few years in the intersection between data science and software
engineering. On the whole, it was a really enjoyable time and I'd like to have
the chance to do so again at some point. One of the least enjoyable experiences
from that time was to deal with big CSV exports. Unfortunately, this file format
is still very common in the data science space. It is easy to understand why --
it seems to be ubiquitous, present everywhere, it's human-readable, it's less
verbose than options like JSON and XML, it's super easy to produce from almost
any tool. What's not to like?

**Edited section**: In hindsight, the title of this post is perhaps too
controversial, and makes it too easy to miss the point. If you're exporting CSV
to end users, to be consumed in spreadsheets, I too would probably just go for
CSV. Please consider something else if you can reasonably expect your users to
want to work with the data with tools like spark, pandas, R, polars or if it
matters to you that people can make robust integrations against your data export.
This post was discussed in this [hacker news](https://news.ycombinator.com/item?id=39814334)
thread.

CSV is (usually) underspecified
--

Sure, [RFC4180](https://datatracker.ietf.org/doc/html/rfc4180) _exists_, but in
practice, CSV is actually a family of file formats that have been in use since
the early 1970s. If a file has a `.csv`-suffix, you don't actually have all of
the information that you require in order to parse it correctly, it's severely
underspecified and in practice, you'll need to open the file and look at it
in order to load the data into a programming environment. Here are some issues
you're likely to encounter in the wild:

- What does missing data look like? The empty string, `NaN`, `0`, `1/1-1970`,
  `null`, `nil`, `NULL`, `\0`?
- What date format will you need to parse? What does `5/5/12` mean?
- How multiline data has been written? Does it use quotation marks, properly
  escape those inside multiline strings, or maybe it just expects you to count
  the delimiter and by the way can delimiters occur inside bare strings?

One of the infurating things about the format is that things often break in ways
that tools can't pick up and tell you about, leading to data corruption instead
of an error. I remember spending hours trying to identify an issue that caused
columns to "shift" around 80% into a 40GB CSV file, and let me tell you, that
just isn't fun. In the end, this came down to a problem that needed to be fixed
in the source, which was producing invalid CSVs, and I wasn't able to work
around the issue using spark on my end, because I needed to process and fix the
records serially to avoid the issue and at that point, why would I want to use a
cluster anyway.

CSV files have terrible compression and performance
--

If you start building something that's producing or consuming CSV files, you
quickly discover that it's annoying to ship them around. Storage is cheap, but
performance matters and shipping around 50GB files take a lot of time.

The next logical move from there is to tack on compression and end up with
`.csv.gz` or `.csv.zip` or some other format that's essentially still CSV.
For the type of data that we use CSV for, this often leads to amazing
compression, perhaps a factor of 10 or 20. Unfortunately, this leads to
vastly more expensive loading and querying of the files. The worst case is if
you need to query for something near the tail end of the file -- the file now
_must_  be read serially, there's no way to seek to somewhere close to where
the data must be. This is perhaps fine if you're going to read all of the
records every time the file is loaded, but even then you're still going to be
paying with performance, it'll take a long time to uncompress big files and
materialize the data in memory. All of the textual data in the file must be
uncompressed and moved to RAM.

Another issue is related to data types. Most CSV readers will read
`"2024-03-24T21:39:23.930074+01:00"` into a 32 character long string, which may
be well in excess of 32 bytes, depending on how a string is represented in
memory in your programming environment (in Python, for example, this string
weighs 81 bytes). Then it'll hopefully be parsed into an 8 byte integer and
one byte timezone offset, and we do the reverse when we serialize again. This is
a lot of wasted effort, compared to just storing the 8 byte integer and
the one byte offset to begin with. If you work in an environment like pandas,
where you want to materialize the whole data set in memory before you process
it, this explosion in size quickly limits how much data you can actually process
at all, before reaching for a more complex tool, like spark.

Numerical columns may also be ambigious, there's no way to know if you can read
a numerical column into an integral data type, or if you need to reach for a
float without first reading all the records. There's tons of variations in how
we serialize and deserialize bools too. Chances are pretty good that you'll
spend quite a while looking at your file before you can parse it correctly.

There's a better way
--

Actually, there are many file formats that are more suitable to working with
tabular data. I'm a big fan of
[Apache Parquet](https://en.wikipedia.org/wiki/Apache_Parquet) as a good default.
You give up human readable files, but what you gain in return is incredibly
valuable:

- Self-describing files that contain their own schema so data is loaded with
  the right data types automatically.
- Really good compression properties, competetive with `.csv.gz` when run-length
  encoding works well for the data.
- Effortless and super fast loading of data into memory, since the files contain
  their own schema, you do not need to sit down and work out data types before
  loading, you simply ask the file.
- You only pay for the columns that you actually load, unused columns do not
  need to be read from disk/network. This means you can offer incredibly wide
  tables and let the user specify columns on loading from the network, rather
  than making one export for each permutation of columns that's requested.
- Support for complex data types, like record types or arrays.

There are other binary data formats that also work really well, but for the use
case where people often reach for CSV, parquet is easily my favorite. If you
absolutely must do streaming writes with record-oriented data, perhaps you
should look into something like [Avro](https://avro.apache.org/) instead.

Backing it up with numbers: Compression
--

I've claimed that parquet is a vastly superior file format to CSV, both when it
comes to compression, convenience and performance so let's do some experiments
to back that up. I'm going to be presenting some file size and timing
information and I'll be using [pandas](https://pandas.pydata.org/) and
[polars](https://pola.rs/) for my examples, the code is written run using
IPython.

To get some numbers, I've downloaded
[this football dataset](https://www.kaggle.com/datasets/hikne707/big-five-european-soccer-leagues/data)
from kaggle, containing 44269 football match scores from 1995 to 2020. This is a
3.7MB CSV file, containing 1 date column, a country column, team names columns
and other than that primarily small ints, a total of 14 columns.

Let's take a look at what kind of compression we can achieve by transforming it
into `.csv.gz` and `.pq` first. This is the code I used to load the file and
transform it into parquet:

``` python
dtype = {
    'Team 1': 'category',
    'FT': 'category',
    'HT': 'category',
    'Team 2': 'category',
    'Round': 'int8', 'Year': 'int16',
    'Country': 'category',
    'FT Team 1': 'int8',
    'FT Team 2': 'int8',
    'HT Team 1': 'int8',
    'HT Team 2': 'int8',
    'GGD': 'int8',
    'Team 1 (pts)': 'int8',
    'Team 2 (pts)': 'int8',
}
date_fmt = '(%a) %d %b %Y (W%W)'
df = pd.read_csv('BIG FIVE 1995-2019.csv', dtype=dtype).assign(
    Date=lambda df: pd.to_datetime(df.Date, format=date_fmt)
)
df.to_parquet('football.pq')
```

Notice how the date column has a somewhat annoying format that looks like this:
`"(Sat) 19 Aug 1995 (W33)"` -- it already took me quite a while to find the
correct format string to parse that, which I wouldn't have had to do if this was
a binary file format with native support for timestamps. Let's take a look at
how the file sizes came out:

``` shellsession
du -hs BIG\ FIVE\ 1995-2019.csv BIG\ FIVE\ 1995-2019.csv.gz football.pq
3.7M	BIG FIVE 1995-2019.csv
472K	BIG FIVE 1995-2019.csv.gz
376K	football.pq
```

In this case, the `.pq` ended up being smaller than the `.csv.gz`.

Backing it up with numbers: Performance
--
Let's check the relative time difference it takes to load both into memory:

```ipython
%timeit df = pd.read_parquet("football.pq")
# 2.26 ms ± 60.8 µs per loop (mean ± std. dev. of 7 runs, 100 loops each)

%%timeit
df = pd.read_csv("BIG FIVE 1995-2019.csv.gz", dtype=dtype).assign(
    Date=lambda df: pd.to_datetime(df.Date, format=date_fmt)
)
# 47.1 ms ± 380 µs per loop (mean ± std. dev. of 7 runs, 10 loops each)

%%timeit
df = pd.read_csv("BIG FIVE 1995-2019.csv", dtype=dtype).assign(
    Date=lambda df: pd.to_datetime(df.Date, format=date_fmt)
)
# 41.8 ms ± 880 µs per loop (mean ± std. dev. of 7 runs, 10 loops each)
```

To summarize, in this case:

- The `.pq` file is smaller than the CSV by a factor of about 10, and it's
  also smaller than the `.csv.gz`.
- The `.pq` file is faster to load by a factor of about 25 compared to the
  `.csv.gz` and a factor of around 19 compared to the CSV.
- I can load the `.pq` file with a single instruction, not knowing anything
  about the file up front, whereas I need to figure out the data types and
  date formats up front for both the other options.

Just to really drive the point home, let's find out how long it takes to
check how many matches Newcaste United FC have won in this data set with a query
using polars, and run it both against the CSV and against the parquet.

``` ipython
home_wins = (
        (pl.col("Team 1") == "Newcastle United FC ") &
        (pl.col("FT Team 1") > pl.col("FT Team 2"))
)
away_wins = (
        (pl.col("Team 2") == "Newcastle United FC ") &
        (pl.col("FT Team 2") > pl.col("FT Team 1"))
)
where = home_wins | away_wins
count = pl.col("Team 1").count().alias("wins")


%timeit pl.scan_csv("BIG FIVE 1995-2019.csv"
  ).filter(where).select(count).collect()
# 1.71 ms ± 37.2 µs per loop (mean ± std. dev. of 7 runs, 100 loops each)
%timeit pl.read_csv("BIG FIVE 1995-2019.csv.gz"
  ).lazy().filter(where).select(count).collect()
# 9.44 ms ± 29.7 µs per loop (mean ± std. dev. of 7 runs, 100 loops each)
%timeit pl.scan_parquet("football.pq"
  ).filter(where).select(count).collect()
# 647 µs ± 6.37 µs per loop (mean ± std. dev. of 7 runs, 1,000 loops each)
```

Note that polars does not allow us to lazy-read a compressed CSV, it needs to
unpack the whole thing anyway, so in order to run a lazy query we need to read
the whole file. With the parquet file, we're now only reading 4 columns and
leaving the majority of them on disk and it's significantly faster than the CSV
file that occupies much more disk space.

Conclusion
--

Of course, we can't conclude that you should _never_ export to CSV. If your
users are just going to try to find the quickest way to turn your data into CSV
anyway, there's no reason why you shouldn't deliver that. But it's a super
fragile file format to use for anything serious like data integration between
systems, so stick with something that at the very least has a schema and is more
efficient to work with.
