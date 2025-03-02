+++
title = "Why would I use DuckDB for that?"
date = "2025-03-02"
tags = ["data", "duckdb", "postgres", "sql"]
+++

The past few weeks I've been experimenting with [DuckDB](https://duckdb.org/), and as a consequence I've ended up talking about it a lot as well. I'm not going to lie, I really like it! However, experienced programmers will rightly be skeptical to add new technology that overlaps with something that already works great. So why not just use postgres?

Well, I really like postgres too, and I think you should consider just using it! But despite both of these technologies being all about tabular data, they're not really for the same kinds of problems. I think DuckDB is primarily an analysis or ELT tool, and it really excels in this space. postgres _can_ do a lot of the things that DuckDB can do, but not nearly as fast or easily. I wouldn't want to use DuckDB for a transactional workload, so it's not going to replace postgres for anything that I use it for.

I want to do some basic tests, verify that my understanding is correct and be able to back up my claims with some numbers. So I've downloaded some data of from [data.entur.no](https://data.entur.no/) again, namely the Norwegian national real-time recordings for public transit data for January and February 2025. I wrote about this data set in [an earlier blogpost](https://arktekk.no/blogs/2025_entur_realtimedataset), if you want to learn more about it.

If you want to follow along, you can download the DuckDB file from [here](https://kaaveland-bus-eta-data.hel1.your-objectstorage.com/all.db) (5GB download).

This is a jupyter notebook, so we'll be mixing code and prose, and show lots of output from programs. Let's get our bearings quickly:


```python
import duckdb

db = duckdb.connect('all.db')

%load_ext sql
%config SqlMagic.displaylimit=50
%sql db --alias duckdb

%sql select count() from arrivals;
```

<span style="None">Running query in &#x27;duckdb&#x27;</span>

<table>
    <thead>
        <tr>
            <th>count_star()</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>85079666</td>
        </tr>
    </tbody>
</table>

So we have about 85 million rows in here, on this schema:


```sql
%%sql
DESCRIBE ARRIVALS
```


<span style="None">Running query in &#x27;duckdb&#x27;</span>

<table>
    <thead>
        <tr>
            <th>column_name</th>
            <th>column_type</th>
            <th>null</th>
            <th>key</th>
            <th>default</th>
            <th>extra</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>recordedAtTime</td>
            <td>TIMESTAMP WITH TIME ZONE</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>lineRef</td>
            <td>VARCHAR</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>directionRef</td>
            <td>VARCHAR</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>operatingDate</td>
            <td>DATE</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>vehicleMode</td>
            <td>VARCHAR</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>extraJourney</td>
            <td>BOOLEAN</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>journeyCancellation</td>
            <td>BOOLEAN</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>stopPointRef</td>
            <td>VARCHAR</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>sequenceNr</td>
            <td>BIGINT</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>stopPointName</td>
            <td>VARCHAR</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>originName</td>
            <td>VARCHAR</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>destinationName</td>
            <td>VARCHAR</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>extraCall</td>
            <td>BOOLEAN</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>stopCancellation</td>
            <td>BOOLEAN</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>estimated</td>
            <td>BOOLEAN</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>aimedArrivalTime</td>
            <td>TIMESTAMP WITH TIME ZONE</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>arrivalTime</td>
            <td>TIMESTAMP WITH TIME ZONE</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>aimedDepartureTime</td>
            <td>TIMESTAMP WITH TIME ZONE</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>departureTime</td>
            <td>TIMESTAMP WITH TIME ZONE</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>datedServiceJourneyId</td>
            <td>VARCHAR</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>dataSource</td>
            <td>VARCHAR</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
        <tr>
            <td>dataSourceName</td>
            <td>VARCHAR</td>
            <td>YES</td>
            <td>None</td>
            <td>None</td>
            <td>None</td>
        </tr>
    </tbody>
</table>



This database file is about 5GB:


```python
!du -hs all.db
```

    5,1G	all.db


I want to put this in a postgres database, so we can do some comparisons. I've set up postgres-17 on my machine, from the [postgres apt](https://wiki.postgresql.org/wiki/Apt). I'm going to put the binaries on PATH, so we can easily make our own postgres instance. This machine has 64GB RAM, and we're going to be the only ones using it, so we can give postgres a lot of resources.


```python
import os
import string
import random
os.environ['PATH'] = '/usr/lib/postgresql/17/bin:' + os.environ['PATH']
# Generate a random password and set it in the env so that all the postgres libs will find it.
os.environ['PGPASSWORD'] = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
```

Having done that, we can use `initdb` to set up a postgres cluster/instance in the `pgtemp` directory under the current working directory:

```bash
%%bash

# Create a databasecluster where:
# superuser is named postgres
# each connection/worker can use 8GB RAM
# the buffer manager can use 24GB RAM to cache tables
# in the pgtemp directory
initdb -U postgres \
  --set work_mem=8GB \
  --set shared_buffers=24GB \
  --set maintenance_work_mem=8GB \
  --set listen_addresses=127.0.0.1 \
  --set port=5433 \
  --set unix_socket_directories="$(pwd)/pgsockets" \
  -D pgtemp
```

    ...
    Success. You can now start the database server using:
    
        pg_ctl -D pgtemp -l logfile start
    ...

Let's double-check the settings we got, so that we won't be surprised later if we somehow got the default `work_mem`:


```python
!grep -E 'work_mem|shared_buffers|listen' pgtemp/postgresql.conf
```

    listen_addresses = '127.0.0.1'		# what IP address(es) to listen on;
    shared_buffers = 24GB			# min 128kB
    work_mem = 8GB				# min 64kB
    #hash_mem_multiplier = 2.0		# 1-1000.0 multiplier on hash table work_mem
    maintenance_work_mem = 8GB		# min 64kB
    #autovacuum_work_mem = -1		# min 64kB, or -1 to use maintenance_work_mem
    #logical_decoding_work_mem = 64MB	# min 64kB
    #wal_buffers = -1			# min 32kB, -1 sets based on shared_buffers


Looks good, let's start it!


```python
!mkdir -p pgsockets
!pg_ctl -D pgtemp -l pg.log start
```

    waiting for server to start.... done
    server started


Now we have a postgres on `127.0.0.1:5433`! Let's attach DuckDB to it so we can easily put the data in there. We will create an unlogged table that doesn't generate transaction logs, since they're not useful for this experiment. It should make it a bit faster to insert data into it. It also means that this table would essentially be lost if our postgres crashed, so think carefully before doing this on something important.


```sql
%%sql

ATTACH 'dbname=postgres user=postgres host=127.0.0.1 port=5433' AS pgtemp (TYPE postgres);

CREATE TABLE pgtemp.arrivals(
    recordedAtTime TIMESTAMP WITH TIME ZONE,
    lineRef VARCHAR,
    directionRef VARCHAR,
    operatingDate DATE,
    vehicleMode VARCHAR,
    extraJourney BOOLEAN,
    journeyCancellation BOOLEAN,
    stopPointRef VARCHAR,
    sequenceNr BIGINT,
    stopPointName VARCHAR,
    originName VARCHAR,
    destinationName VARCHAR,
    extraCall BOOLEAN,
    stopCancellation BOOLEAN,
    estimated BOOLEAN,
    aimedArrivalTime TIMESTAMP WITH TIME ZONE,
    arrivalTime TIMESTAMP WITH TIME ZONE,
    aimedDepartureTime TIMESTAMP WITH TIME ZONE,
    departureTime TIMESTAMP WITH TIME ZONE,
    datedServiceJourneyId VARCHAR,
    dataSource VARCHAR,
    dataSourceName VARCHAR);
```


<span style="None">Running query in &#x27;duckdb&#x27;</span>

Let's make it unlogged:

```sql
%%sql
CALL postgres_execute('pgtemp', 'ALTER TABLE arrivals SET UNLOGGED;')
```


<span style="None">Running query in &#x27;duckdb&#x27;</span>



<table>
    <thead>
        <tr>
            <th>Success</th>
        </tr>
    </thead>
    <tbody>
    </tbody>
</table>



Since our table schemas match, we should be able to use DuckDB to bulkload this efficiently. Let's give it a go:


```sql
%%sql
INSERT INTO pgtemp.arrivals BY NAME SELECT * FROM arrivals;
```


<span style="None">Running query in &#x27;duckdb&#x27;</span>





<table>
    <thead>
        <tr>
            <th>Count</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>85079666</td>
        </tr>
    </tbody>
</table>



Okay, the first thing I want to know is the size of the database after doing this, let's check:


```python
!du -hs pgtemp
```

    18G	pgtemp


This is not surprising to me, columnar storage formats are much easier to compress efficiently than row storage formats, like the one used by postgres. This should fit in memory for postgres, it has 24GB RAM for shared buffers (and a generous 8GB for sorting and things like that). Let's time some basic operations in DuckDB vs postgres. We will limit DuckDB to 16GB RAM, so my machine can have something left over for running... everything else.


```python
# limits for DuckDB
%sql set memory_limit = '16GB';
%sql set threads = 11; -- CPU has 12 physical cores, Ryzen 9 5900X.
%time db.sql("select dataSource, count(*) from arrivals group by dataSource").df()
%time db.sql("""call postgres_query('pgtemp', 'select "dataSource", count(*) from arrivals group by "dataSource"')""").df()
```

    CPU times: user 316 ms, sys: 11.3 ms, total: 327 ms
    Wall time: 31.6 ms

    CPU times: user 11.3 s, sys: 854 μs, total: 11.3 s
    Wall time: 11.3 s


I discarded the result set output from this, keeping only the execution times. For this very simple example, DuckDB can do it in 31.6ms and postgres needs 11.3 seconds.

This is a very unfair comparison, though. In this particular instance, DuckDB looks only at 1 column, and it is probably dictionary-encoded and run length encoded, similarly to how Arrow and Parquet does it. You can read a bit more about that [here](https://arrow.apache.org/blog/2019/09/05/faster-strings-cpp-parquet/) and [here](https://wesmckinney.com/blog/python-parquet-multithreading/). This kind of query and data distribution is essentially a best-case for columnar storage formats. An index would help postgres here, but it would likely be significantly bigger than the column DuckDB has stored, and therefore still slower.

It may be much more fair to try to do a group by on a column where such shortcuts aren't possible. Let's count registrations by hour of day, which forces both implementations to look at all values of the `recordedAtTime` column.


```python
q = 'select count(*), extract(hour from "recordedAtTime") as hour from arrivals group by 2'
%time db.sql(q).df()
%time db.sql(f"call postgres_query('pgtemp', '{q}')").df()
```

    CPU times: user 18 s, sys: 0 ns, total: 18 s
    Wall time: 1.65 s

    CPU times: user 5.97 s, sys: 0 ns, total: 5.97 s
    Wall time: 5.97 s


This time, the difference is much less drastic. DuckDB needs 1.65s and postgres can do it in 6s. For this query, DuckDB needed to investigate every value in the column, there's much less work that it can simply skip. Looking at the CPU time information, it seems obvious that DuckDB is using much more CPU to do this calculation than postgres, due to parallelization.

Let's try one that is a little tougher still. Let's use a window function to calculate the time from arrival at one stop, to the next and calculate some nonsense statistics about it. This will force both databases to do a lot of work using several columns. We may be able to make useful indexes for postgres here, but we'll try without first (I am expecting postgres to summarily lose this one without an index).


```python
q = '''
with times as (
    select 
      extract(epoch from 
          lead("arrivalTime", 1) over (partition by "datedServiceJourneyId" order by "sequenceNr") 
           - "arrivalTime"
      ) as timedelta
    from arrivals
)
select
    max(timedelta), min(timedelta), sum(timedelta) / count(*) -- avg in postgres and mean in duckdb
from times
'''
%time db.sql(q).df()
%time db.sql(f"call postgres_query('pgtemp', '{q}')").df()
```


    CPU times: user 2min 40s, sys: 9.72 s, total: 2min 50s
    Wall time: 15.7 s

    CPU times: user 8min 15s, sys: 52.2 ms, total: 8min 15s
    Wall time: 8min 15s


Wow, that's a big difference. DuckDB spent 15.7s and postgres spent 8 mins 15s. I am not sure why the difference is so big in this case. Even a table scan should be quite quick for postgres now, the data is certainly in RAM already. This difference is so large that I can't explain it without involving disk usage.

In this case, it would have been much faster to pull all the data out from postgres and into DuckDB and do the aggregation there. I'm betting we can help postgres by making an index that matches the partition of the window function. Let's do that.


```python
index = 'create index on arrivals("datedServiceJourneyId", "sequenceNr");'
%time db.execute(f"call postgres_execute('pgtemp', '{index}');")
```


    CPU times: user 3min 3s, sys: 954 ms, total: 3min 4s
    Wall time: 3min 3s


3 minutes, less time than running the query originally. Let's try the query one more time:


```python
%time db.sql(f"call postgres_query('pgtemp', '{q}')").df()
```

    CPU times: user 8min 16s, sys: 432 ms, total: 8min 17s
    Wall time: 8min 16s


Right, the index was not useful. Perhaps because the table fits in memory anyway. I made sure to `ANALYZE;` and try again, just in case. On disk, this index is larger than the entire DuckDB file, creating it increased the size of the `pgtemp` postgres cluster to 25GB:


```python
!du -hs pgtemp
```

    25G	pgtemp


One variation that we haven't tried yet, is to just run the query in DuckDB, but against the postgres table (meaning DuckDB will have to delegate some work to postgres, or copy out all the data).


```python
%time db.sql(q.replace("arrivals", "pgtemp.arrivals")).df()
```

    CPU times: user 3min, sys: 13.6 s, total: 3min 14s
    Wall time: 25.7 s


Right, that's very interesting, that's 25.7s compared to the 8 minutes of running purely in postgres or the 13.4s of running purely against DuckDB. This would create load and IO on the postgres database server, naturally, but maybe that's a good way to offload the heavy computational work onto the applicationserver?

I'm going to go look some more into what's happening in postgres here, it does not make sense to me that it can take 8 minutes to run this query if everything's in memory. I'll head over to `psql` and check out what `explain (analyze on, buffers on)` tells me.


```sql
postgres=# explain (analyze on, buffers on) with times as (
    select 
      extract(epoch from 
          lead("arrivalTime", 1) over (partition by "datedServiceJourneyId" order by "sequenceNr") 
           - "arrivalTime"
      ) as timedelta
    from arrivals
)
select
    max(timedelta), min(timedelta), sum(timedelta) / count(*) -- avg in postgres and mean in duckdb
from times;
                                                                  QUERY PLAN                                                                   
-----------------------------------------------------------------------------------------------------------------------------------------------
 Aggregate  (cost=18207075.69..18207075.71 rows=1 width=96) (actual time=506560.516..506560.517 rows=1 loops=1)
   Buffers: shared hit=2729 read=2314831, temp read=813011 written=813012
   ->  WindowAgg  (cost=14377525.67..16505053.45 rows=85101112 width=90) (actual time=467725.139..501383.481 rows=85079666 loops=1)
         Buffers: shared hit=2729 read=2314831, temp read=813011 written=813012
         ->  Sort  (cost=14377525.65..14590278.43 rows=85101112 width=66) (actual time=467725.100..474901.976 rows=85079666 loops=1)
               Sort Key: arrivals."datedServiceJourneyId", arrivals."sequenceNr"
               Sort Method: external merge  Disk: 6504088kB
               Buffers: shared hit=2729 read=2314831, temp read=813011 written=813012
               ->  Seq Scan on arrivals  (cost=0.00..3168571.12 rows=85101112 width=66) (actual time=199.763..17347.756 rows=85079666 loops=1)
                     Buffers: shared hit=2729 read=2314831
 Planning:
   Buffers: shared hit=22
 Planning Time: 0.371 ms
 JIT:
   Functions: 11
   Options: Inlining true, Optimization true, Expressions true, Deforming true
   Timing: Generation 0.608 ms (Deform 0.255 ms), Inlining 64.518 ms, Optimization 68.888 ms, Emission 66.374 ms, Total 200.389 ms
 Execution Time: 507455.248 ms
```

Aha, so it's sorting on disk. That means it may help to increase `work_mem`. I'll try to double it to 16GB with `set work_mem='16GB';` (and close some applications on this machine). I will also create an index that includes all the 3 columns this query uses, to try to get an `Index Only Scan`:

```sql
postgres=# create index on arrivals("datedServiceJourneyId", "sequenceNr", "arrivalTime");
CREATE INDEX
postgres=# explain (analyze on, buffers on) with times as (
    select 
      extract(epoch from 
          lead("arrivalTime", 1) over (partition by "datedServiceJourneyId" order by "sequenceNr") 
           - "arrivalTime"
      ) as timedelta
    from arrivals
)
select
    max(timedelta), min(timedelta), sum(timedelta) / count(*) -- avg in postgres and mean in duckdb
from times;
                                                                                               QUERY PLAN                                                                                                    
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 Aggregate  (cost=8735893.91..8735893.93 rows=1 width=96) (actual time=46947.869..46947.870 rows=1 loops=1)
   Buffers: shared hit=51347699 read=947841
   ->  WindowAgg  (cost=0.77..7034300.63 rows=85079664 width=90) (actual time=61.489..41859.920 rows=85079666 loops=1)
         Buffers: shared hit=51347699 read=947841
         ->  Index Only Scan using "arrivals_datedServiceJourneyId_sequenceNr_arrivalTime_idx" on arrivals  (cost=0.69..5120008.19 rows=85079664 width=66) (actual time=61.471..12268.748 rows=85079666 loops=1)
               Heap Fetches: 0
               Buffers: shared hit=51347699 read=947841
 Planning:
   Buffers: shared hit=22 read=1 dirtied=2
 Planning Time: 14.759 ms
 JIT:
   Functions: 10
   Options: Inlining true, Optimization true, Expressions true, Deforming true
   Timing: Generation 0.499 ms (Deform 0.116 ms), Inlining 11.793 ms, Optimization 28.170 ms, Emission 21.494 ms, Total 61.955 ms
 Execution Time: 46950.351 ms
(15 rows)

```

That's more like it. So if we back the query with an appropriate index, postgres can run this query in 47s, which is quite close to DuckDB, considering that it doesn't use all my cores. This index is 7504MB, though, and took some minutes to create. In other words, I need to know that I must back this query with an index to get good performance. If this was a database server with some transactional workload, it could have consequences to run the query without the index. We're also relying on the index being in memory to get good performance here. 

I'm going to clean up my mess here and call it a day. I do think it's probably true that postgres can do almost everything that DuckDB can do. But I can definitely see a case for having both, they complement each others capabilities really well.


```python
!pg_ctl stop -D pgtemp
!rm -rf pgtemp
```

    waiting for server to shut down...... done
    server stopped


Thanks for reading!
