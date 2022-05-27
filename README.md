# KenshiWikiScraper

This script scrapes information from
the [Kenshi](https://store.steampowered.com/app/233860/Kenshi/) [wiki](https://kenshi.fandom.com/wiki/Kenshi_Wiki) for
use in [KenshiCalc](https://github.com/Bobbias/KenshiCalc). It is intended to be included as a submodule, and run once
when installing in order to generate the necessary database file and download the necessary images.

## Dependencies

[apsw](https://github.com/rogerbinns/apsw) - For SQLite
[requests](https://github.com/psf/requests) - For making simple HTTP requests
[bs4](https://www.crummy.com/software/BeautifulSoup/) - For scraping data from the wiki
[colorlog](https://github.com/borntyping/python-colorlog) - For adding ansi color codes to console logging output
[pygments](https://github.com/pygments/pygments) - Used for syntax highlighting when outputting raw HTML during
debugging
[returns](https://github.com/dry-python/returns) - Functional programming style return values

## Usage

This script is fully automated, so running should be as simple as running it from the command line.

### Optional Command line arguments

`main.py [-d|--debug[=on|true|off|false|verbose]] [output]`

`on` and `true` both enable debugging output, while `off` and `false` disable it.

`verbose` enables verbose output which will print out a lot of HTML to the console. Only intended to be used when
absolutely necessary due to the sheer amount of output it generates.

`debug` defaults to `false`

`output` is the name of the database file to generate. If it is empty, the default filename is `KenshiData`.

## License

Copyright 2022 Bobbias

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.