import os

AUTHOR = 'Robin Kåveland'
SITENAME = "Robin's blog"
SITETITLE = AUTHOR
SITESUBTITLE = "Software engineer"
SITEDESCRIPTION = ""
SITEURL = ''
SITELOGO = '/images/face.png'
STATIC_PATHS = ['images', 'CNAME']

ROBOTS = "index, follow"
PATH = 'content'

TIMEZONE = 'Europe/Oslo'

DEFAULT_LANG = 'en'
DEFAULT_DATE_FORMAT = '%Y-%m-%d'
MAIN_MENU = True

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

# Blogroll
LINKS = ()
PAGE_PATHS = ['pages']

# Social widget
SOCIAL = (('github', 'https://github.com/kaaveland'),
          ('twitter', 'https://twitter.com/robinkaveland'))

DEFAULT_PAGINATION = 20

# Uncomment following line if you want document-relative URLs when developing
#RELATIVE_URLS = True

THEME = os.path.join(
    os.path.dirname(__file__),
    'Flex'
)
