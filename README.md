Blog
==

This project is my blog. It's a statically generated blog, generated with
[pelican](https://docs.getpelican.com/en/latest/).

It uses [pdm](https://github.com/pdm-project/pdm) to configure the python
environment that is required in order to build it. To get started, install
pdm in any way you prefer, then:


``` shell
pdm venv create 3.11 -w venv && pdm sync && eval $(pdm venv activate in-project)
```

The blog uses the [Flex](https://github.com/alexandrevicenzi/Flex), clone it
into this directory:

``` shellsession
git clone git@github.com:alexandrevicenzi/Flex.git
```


To serve locally while you work:

``` shell
eval $(pdm venv activate in-project) && make devserver
```

To publish to github pages, push to `main`.
