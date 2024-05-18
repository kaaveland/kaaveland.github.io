Blog
==

This project is my blog. It's a statically generated blog, generated with
[hugo](https://gohugo.io/).

The blog uses the excellent [PaperMod](https://github.com/adityatelange/hugo-PaperMod) theme.

Install hugo by following instructions from the [hugo website](https://gohugo.io/getting-started/installing/). Then
install the theme, you can use [setup.sh](/setup.sh) to do this, if you're OK with using git submodules.



To serve locally while you work:

``` shell
hugo serve
```

To build the page:

``` shell
hugo
```

The output ends up in the `public` directory.

To publish to github pages, push to `main`.
