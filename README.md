Blog
==

This project is my blog. It's a statically generated blog, generated with
[pelican](https://docs.getpelican.com/en/latest/).

It uses [pdm](https://github.com/pdm-project/pdm) to configure the python
environment that is required in order to build it. To get started, install
pdm in any way you prefer, then:

``` shell
pdm venv create -w venv && pdm venv activate in-project
```

To serve locally while you work:

``` shell
pdm venv activate in-project && make devserver
```

To publish to github pages:

``` shell
pdm venv activate in-project && make github
```
