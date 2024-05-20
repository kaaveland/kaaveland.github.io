+++
title = "Projects"
slug = "projects"
date = "2024-05-06"
+++

I have a few projects on my GitHub that I sometimes work on:

- [eugene](https://github.com/kaaveland/eugene/) is a postgres SQL migration checker, sort of like [shellcheck](https://www.shellcheck.net/) but for
  database migration scripts. It can parse SQL, or trace the effects of the scripts in a database
  and report about things that could lead to outages in production. It has a
  fancy documentation site [here](https://kaveland.no/eugene).
- [pyarrowfs-adlgen2](https://github.com/kaaveland/pyarrowfs-adlgen2) is a connector between [Apache Arrow](arrow.apache.org) and
  [Azure Data Lake Gen2](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-introduction). It's good for reading and writing files in storage accounts with
  hierarchial namespace support over the network, and it's pretty fast compared
  to alternatives like [fsspec/adlfs](https://github.com/fsspec/adlfs/)
- [advent-of-code-rs](https://github.com/kaaveland/advent-of-code-rs) are my Advent of Code solutions in Rust. I've finished many of the seasons and I try
  to make the solutions run fast.
