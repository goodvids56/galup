galup - a gallery-dl to Archive.org uploader
============================================

![Unit Tests](https://github.com/goodvids56/galup/workflows/Unit%20Tests/badge.svg)
![Lint](https://github.com/goodvids56/galup/workflows/Lint/badge.svg)

> [!IMPORTANT]
> **This is a fork.** galup ([goodvids56/galup](https://github.com/goodvids56/galup)) is an unofficial fork of [Tubeup by the Bibliotheca Anonoma](https://github.com/bibanon/tubeup).
> It replaces the downloader with [gallery-dl](https://codeberg.org/mikf/gallery-dl). It is not affiliated with or supported by the upstream Tubeup maintainers, gallery-dl or the Internet Archive.
> Please report problems with this fork to [this fork's issue tracker](https://github.com/goodvids56/galup/issues), not to upstream Tubeup.
> Upstream Tubeup, and the `tubeup` package on PyPI, are a different program.

`galup` uses gallery-dl to download images, galleries and other media (from [any site supported by gallery-dl](https://codeberg.org/mikf/gallery-dl/src/branch/master/docs/supportedsites.md)), and then uploads them with all metadata to the Internet Archive using the python module internetarchive.

The original Tubeup was designed by the [Bibliotheca Anonoma](https://github.com/bibanon/bibanon/wiki) to archive videos to the Internet Archive. This fork applies the same approach to everything gallery-dl can download: single posts, galleries, user profiles and so on.

Each post gets its own Archive.org item, identified as `{platform}-{id}` (for example `tiktok-7700361800876920077` or `twitter-1700000000000000001`), just like TubeUp. All files of the post (e.g. every image of a gallery or slideshow) go into that item, together with one `{id}.info.json` file containing the post's metadata, written by gallery-dl's own metadata post processor. When the post's metadata has a thumbnail (e.g. the cover of a TikTok video), it is saved as `{id}.thumbnail.{ext}` too, unless the post is a single image. Files are named `{id}.{ext}`, or `{id}_{num}.{ext}` when a post has several files (e.g. `7700361800876920077_1.jpg`). When gallery-dl doesn't report a post ID, the identifier falls back to `{platform}-{filename}` and the file keeps its original name. Images go to the [Community Images](https://archive.org/details/opensource_image) collection, videos to [Community Video](https://archive.org/details/opensource_movies) and audio to [Community Audio](https://archive.org/details/opensource_audio), unless you choose another collection with `--metadata`.

## Prerequisites

This script strongly recommends Linux or some sort of POSIX system (such as macOS), preferably from a VPS or Linux/Unix shell you have access to.

Recommended system specifications:
- Linux VPS with Python 3.10 or higher, with `pipx` installed
- 2GB of RAM, 100GB of storage or much more for anything other than a few single posts. If your OS drive is too small, `symlink` it to something larger.

## Setup and Installation

Installation via third-party package managers like Homebrew, MacPorts, or Linux system packages (apt, yum, etc.) *is not supported.*

galup is not published on PyPI, so install it from its git repository as shown below. (`pipx install tubeup` installs upstream Tubeup, which is a different program.)


1. Install `pipx` (typically `python3-pipx` or in Arch `python-pipx`), `git` and, optionally, `ffmpeg` (gallery-dl uses it for some formats, such as Pixiv ugoira animations).
   To install ffmpeg in Ubuntu, enable the Universe repository.

For Debian/Ubuntu:

```
    sudo apt install ffmpeg python3-pipx git
```


Then run this to add pipx path to your shell RC file:

```
    pipx ensurepath
```


2. Use pipx to install galup. gallery-dl and internetarchive are installed with it as dependencies, and `--include-deps` also puts their `gallery-dl` and `ia` commands on your path.

```
    pipx install --include-deps git+https://github.com/goodvids56/galup.git
```


3. If you don't already have an Internet Archive account, [register for one](https://archive.org/account/login.createaccount.php) to give the script upload privileges.



4. Configure `internetarchive` with your Internet Archive account.

```
    ia configure
```

You will be prompted for your login credentials for the Internet Archive account you use. Once configured to upload, you're ready to go.


5. Start archiving by running the script on a URL (or multiple URLs) [supported by gallery-dl](https://codeberg.org/mikf/gallery-dl/src/branch/master/docs/supportedsites.md). Depending on the site, this includes single posts, galleries and user profiles.

```
    galup <url>
```

Sites that need a login can use `--username`/`--password` or `--cookies`. Your regular [gallery-dl configuration file](https://codeberg.org/mikf/gallery-dl/src/branch/master/docs/configuration.rst) is loaded as well, so site credentials and options set there are used too.


6. Each archived post gets its own Archive.org item. Check out what you've uploaded at

   `http://archive.org/details/@YOURUSERNAME`.


7. Upgrading

Periodically *before* use, upgrade galup and its python dependencies (including gallery-dl) by running:

```
    pipx upgrade galup --pip-args="--upgrade-strategy eager"
```

## Windows Setup

1. Install WSL2, pick a distribution of your choice. Ubuntu is popular, well-supported and used here as a example.
2. Use Windows Terminal by Microsoft to interact with the WSL2 instance.
3. Fully update the Linux installation.
   ```sudo apt update ; sudo apt upgrade```
4. Install python `pipx`, `git` and optionally `ffmpeg`.
5. Install this fork using steps 2-6 in the Linux configuration guide above and configure `internetarchive` for your Archive.org account.
6. Periodically update your distro repository packages and python packages. This command should be the same or similar to the one in the Linux guide.


## Usage

```
Usage:
  galup <url>... [--username <user>] [--password <pass>]
                  [--metadata=<key:value>...]
                  [--cookies=<filename>]
                  [--proxy <prox>]
                  [--quiet] [--debug]
                  [--use-download-archive]
                  [--output <output>]
                  [--dir <dir>]
                  [--ignore-existing-item]
  galup -h | --help
  galup --version
```
```
Arguments:
  <url>                         gallery-dl compatible URL to download.
                                Check gallery-dl documentation for a list
                                of compatible websites.
  --metadata=<key:value>        Custom metadata to add to the archive.org
                                item.
  --dir <dir>                   Provide a directory for downloads and metadata.
  
Options:
  -h --help                    Show this screen.
  -x --proxy <prox>            Use a proxy while downloading.
  -u --username <user>         Provide a username, for sites that need a login.
  -p --password <pass>         Provide a password, for sites that need a login.
  -a --use-download-archive    Record downloaded files in the download archive.
                               This will download only files not listed in
                               the archive file.
  -q --quiet                   Just print errors.
  -d --debug                   Print all logs to stdout.
  -o --output <output>         gallery-dl filename format string. Defaults to
                               {id}.{extension}, or {id}_{num}.{extension}
                               for posts with several files.
  -i --ignore-existing-item    Don't check if an item already exists on archive.org
```


## Metadata

You can specify custom metadata with the `--metadata` flag.
For example, this script will upload images to the [Community Images collection](https://archive.org/details/opensource_image) by default.
You can specify a different collection with the `--metadata` flag:

```
    galup --metadata=collection:opensource_audio <url>
```

Any arbitrary metadata can be added to the item, with a few exceptions.
You can learn more about archive.org metadata [here](https://archive.org/services/docs/api/metadata-schema/).


### Collections

Archive.org users can upload to these open collections:

* [Community Images](https://archive.org/details/opensource_image) where the identifier is `opensource_image`.
* [Community Audio](https://archive.org/details/opensource_audio) where the identifier is `opensource_audio`.
* [Community Software](https://archive.org/details/open_source_software)  where the identifier is `opensource_software`.
* [Community Texts](https://archive.org/details/opensource) where the identifier is `opensource`.
* [Community Video](https://archive.org/details/opensource_movies) where the identifier is `opensource_movies`.

Note that care should be taken when uploading entire accounts or galleries.
Read the appropriate section [in this guide](https://archive.org/about/faqs.php#Collections) for creating collections, and contact the [collections staff](mailto:collections-service@archive.org) if you're uploading an account or multiple accounts on one subject (art or photography for example). Internet Archive collections staff will either create a collection for you or merge any uploaded items based on the uploader name that are already up into a new collection.

**Dumping entire accounts into the community collections is abusive and may get your account locked.** Since this fork creates one item per post, a single account can produce many items. _Talk to the Internet Archive admins first before doing large uploads; it's better to ask for guidence or help first than run afoul of the rules._

**If you do not own a collection you will need to be added as an admin for that collection if you want to upload to it.** Talk to the collection owner or staff if you need assistance with this.


## Troubleshooting

* Some content is blocked in certain countries. Use the proxy or torrenting/privacy VPN option to use a proxy to bypass this. Sweden and Germany are good countries to bypass geo-restrictions.
* A site isn't working? Check whether plain `gallery-dl <url>` works first. If it doesn't, the problem is in gallery-dl or the site, and it should be reported to [gallery-dl's issue tracker](https://codeberg.org/mikf/gallery-dl/issues).
* Upload taking forever? Getting s3 throttling on upload? galup (like upstream Tubeup) has specifically been tailored to wait the longest possible time before failing, and we've never seen a S3 outage that outlasted the insane wait times set in it. Disabling waits for S3 timeouts won't make the upload work, instead it will leave the downloaded contents on your disk in the downloads folder (`~/.galup/downloads`) because the download will immeaditly fail instead of gracefully waiting. The waits are a safety in case timeouts occur, do not disable them.


## Major Credits (in no particular order)

galup is built on the work of upstream Tubeup and its contributors:

- [emijrp](https://github.com/emijrp/) who wrote the original [youtube2internetarchive.py](https://code.google.com/p/emijrp/source/browse/trunk/scrapers/youtube2internetarchive.py) in 2012
- [Matt Hazinski](https://github.com/matthazinski) who forked emijrp's work in 2015 with numerous improvements of his own.
- Antonizoon for switching the script to library calls rather than functioning as an external script, and many small improvements.
- Small PRs from various people, both in and out of BibAnon.
- vxbinaca for stabilizing download/upload library calls, cleansing item output, subtitles collection, and numerous small improvements over time.
- mrpapersonic for adding logic to check if an item already exists in the Internet Archive and if so skips ingestion.
- [Jake Johnson](https://github.com/jjjake) of the Internet Archive for adding variable collections ability as a flag, switching Tubeup from a script to PyPi repository, ISO-compliant item dates, fixing what others couldn't, and many improvements.
- [Refeed](https://github.com/refeed) for re-basing the code to OOP, turning Tubeup itself into a library. and adding download and upload bar graphs, and squashing bugs.
- [Mike Fährmann](https://codeberg.org/mikf) and contributors for [gallery-dl](https://codeberg.org/mikf/gallery-dl), which this fork uses to download.


## License (GPLv3)

Copyright (C) 2026 Bibliotheca Anonoma

galup is distributed under the same license as upstream Tubeup.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.


## Star History

<a href="https://star-history.dera.page/#goodvids56/galup&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://star-history.dera.page/svg?repos=goodvids56/galup&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://star-history.dera.page/svg?repos=goodvids56/galup&type=Date" />
   <img alt="Star History Chart" src="https://star-history.dera.page/svg?repos=goodvids56/galup&type=Date" />
 </picture>
</a>
