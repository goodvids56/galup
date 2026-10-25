import os
import re
import time
import logging
import collections
import internetarchive

from internetarchive.config import parse_config_file
from datetime import datetime
from gallery_dl import config as gdl_config
from gallery_dl import exception as gdl_exception
from gallery_dl import text as gdl_text
from gallery_dl.job import DownloadJob
from .utils import (get_itemname, get_filename, get_post_name,
                    get_thumbnail_url)
from logging import getLogger
from urllib.parse import urlparse

from galup import __version__


DOWNLOAD_DIR_NAME = 'downloads'

VIDEO_EXTENSIONS = {'mp4', 'webm', 'mkv', 'mov', 'avi', 'flv', 'm4v', 'wmv',
                    'ts', 'mpg', 'mpeg', '3gp'}
AUDIO_EXTENSIONS = {'mp3', 'm4a', 'ogg', 'opus', 'flac', 'wav', 'aac', 'wma'}
IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'avif', 'heic', 'bmp'}

# Profile URLs of uploaders by gallery-dl category, used for the `channel`
# metadata
CHANNEL_URLS = {
    'bluesky': 'https://bsky.app/profile/{username}',
    'deviantart': 'https://www.deviantart.com/{username}',
    'instagram': 'https://www.instagram.com/{username}/',
    'reddit': 'https://www.reddit.com/user/{username}',
    'tiktok': 'https://www.tiktok.com/@{username}',
    'twitter': 'https://x.com/{username}',
}


class GalleryJob(DownloadJob):
    """
    gallery-dl DownloadJob that reports every file it downloads (or finds
    already on disk) together with the post it belongs to, and can skip posts
    whose archive.org item already exists. After the files of a post, it
    downloads the post's thumbnail, if its metadata has one, to
    `{id}.thumbnail.{ext}`.

    Child jobs (e.g. the posts of a user profile) are created by gallery-dl
    with `self.__class__(extractor, parent)`, so the callbacks are inherited
    from the parent job.
    """

    def __init__(self, url, parent=None, on_file=None, should_skip=None):
        DownloadJob.__init__(self, url, parent)
        if parent is not None:
            on_file = parent.on_file
            should_skip = parent.should_skip
        self.on_file = on_file
        self.should_skip = should_skip
        self.post_name = None
        # Metadata and downloaded files of the current post
        self.post_kwdict = None
        self.post_files = []

    def initialize(self, kwdict=None):
        DownloadJob.initialize(self, kwdict)
        if self.on_file is None:
            return
        if not self.hooks:
            self.hooks = collections.defaultdict(list)
        self.register_hooks({'after': self._report_file,
                             'skip': self._report_file})

    def handle_directory(self, kwdict):
        # gallery-dl starts every post with a directory message. Name the post
        # after its ID; this names the post's .info.json, written by
        # gallery-dl's metadata post processor (see
        # `GalUp.generate_gdl_options`), and its archive.org item.
        self.download_thumbnail()
        self.post_name = get_post_name(kwdict)
        self.post_kwdict = kwdict
        self.post_files = []
        kwdict['_galup_post'] = self.post_name
        DownloadJob.handle_directory(self, kwdict)

    def handle_finalize(self):
        try:
            self.download_thumbnail()
        except Exception as exc:
            self.extractor.log.warning('Failed to download thumbnail (%s: %s)',
                                       exc.__class__.__name__, exc)
        DownloadJob.handle_finalize(self)

    def download_thumbnail(self):
        """
        Download the thumbnail of the current post to `{id}.thumbnail.{ext}`,
        once all its files have been downloaded.
        """
        kwdict, self.post_kwdict = self.post_kwdict, None
        if kwdict is None or not self.post_files:
            return
        url = get_thumbnail_url(kwdict)
        if url is None:
            return

        # A post with a single image, named `{id}.{ext}`, is its own
        # thumbnail
        for filepath in self.post_files:
            name, extension = os.path.splitext(os.path.basename(filepath))
            extension = extension[1:].lower()
            if name == self.post_name and \
                    extension not in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
                return

        thumbnail = dict(kwdict)
        gdl_text.nameext_from_url(url, thumbnail)
        if thumbnail.get('extension', '').lower() not in IMAGE_EXTENSIONS:
            # gallery-dl corrects it from the downloaded file if needed
            thumbnail['extension'] = 'jpg'
        thumbnail.pop('num', None)
        thumbnail.update({
            'type': 'thumbnail',
            'file_url': url,
            '_galup_filename': self.post_name + '.thumbnail',
        })
        DownloadJob.handle_url(self, url, thumbnail)

    def handle_url(self, url, kwdict):
        # Used by the default filename format, see `GalUp.generate_gdl_options`
        kwdict['_galup_filename'] = (get_filename(kwdict) or
                                     kwdict.get('filename') or 'file')
        if self.post_name is None:
            self.post_name = get_post_name(kwdict)
        if self.should_skip is not None:
            if self.should_skip(kwdict, self.post_name):
                if self.pathfmt is None:
                    self.initialize(kwdict)
                if self.archive is not None:
                    self.archive.add(kwdict)
                return
        DownloadJob.handle_url(self, url, kwdict)

    def _report_file(self, pathfmt):
        filepath = pathfmt.realpath
        if filepath and os.path.isfile(filepath):
            self.post_files.append(filepath)
            # Where gallery-dl's metadata post processor writes the post's
            # .info.json, without the .info.json extension
            post_basename = pathfmt.realdirectory + pathfmt.clean_path(
                pathfmt.clean_segment(self.post_name))
            self.on_file(filepath, pathfmt.kwdict, self.extractor.url,
                         post_basename)


class GalUp(object):
    class DirError(Exception):
        pass

    def __init__(self,
                 verbose=False,
                 dir_path='~/.galup',
                 ia_config_path=None,
                 output_template=None):
        """
        `galup` (a gallery-dl fork of TubeUp) is a tool to archive images, galleries and
        other media by downloading them with gallery-dl and uploading them to
        archive.org.

        :param verbose:         A boolean, True means all loggings will be
                                printed out to stdout.
        :param dir_path:        A path to directory that will be used for
                                saving the downloaded resources. Default to
                               '~/.galup'.
        :param ia_config_path:  Path to an internetarchive config file, will
                                be used in uploading the file.
        :param output_template: A gallery-dl filename format string that will
                                be used to generate the output filenames.
                                Defaults to `{id}.{extension}`, or
                                `{id}_{num}.{extension}` for posts with
                                several files.
        """
        self.dir_path = dir_path
        self.verbose = verbose
        self.ia_config_path = ia_config_path
        self.logger = getLogger(__name__)
        self.output_template = output_template

        # Just print errors in quiet mode
        if not self.verbose:
            self.logger.setLevel(logging.ERROR)

    @property
    def dir_path(self):
        return self._dir_path

    @dir_path.setter
    def dir_path(self, dir_path):
        """
        Set a directory to be the saving directory for resources that have
        been downloaded.

        :param dir_path:  Path to a directory that will be used to save the
                          videos, if it not created yet, the directory
                          will be created.
        """
        try:
            dir_path = os.fspath(dir_path)
        except TypeError as exc:
            raise GalUp.DirError(
                'Download directory must be a string or path-like object.'
            ) from exc

        if not dir_path or not dir_path.strip():
            raise GalUp.DirError('Download directory must not be empty.')

        extended_usr_dir_path = os.path.abspath(os.path.expanduser(dir_path))
        downloads_dir_path = os.path.join(extended_usr_dir_path,
                                          DOWNLOAD_DIR_NAME)

        if (os.path.exists(extended_usr_dir_path) and
                not os.path.isdir(extended_usr_dir_path)):
            raise GalUp.DirError(
                'Download root path "%s" already exists as a file. '
                'Choose a different --dir to avoid data loss.'
                % extended_usr_dir_path)

        if os.path.exists(downloads_dir_path) and not os.path.isdir(downloads_dir_path):
            raise GalUp.DirError(
                'Download path "%s" already exists as a file. '
                'Choose a different --dir to avoid data loss.'
                % downloads_dir_path)

        try:
            os.makedirs(extended_usr_dir_path, exist_ok=True)
            os.makedirs(downloads_dir_path, exist_ok=True)
        except OSError as exc:
            raise GalUp.DirError(
                'Cannot create download directory "%s": %s'
                % (downloads_dir_path, exc)
            ) from exc

        self._dir_path = {
            'root': extended_usr_dir_path,
            'downloads': downloads_dir_path
        }

    def get_resource_basenames(self, urls,
                               cookie_file=None, proxy_url=None,
                               gdl_username=None, gdl_password=None,
                               use_download_archive=False,
                               ignore_existing_item=False):
        """
        Download urls with gallery-dl and get the downloaded files by post.

        :param urls:                  A list of urls that will be downloaded with
                                      gallery-dl.
        :param cookie_file:           A cookie file for gallery-dl.
        :param proxy_url:             A proxy url for gallery-dl.
        :param gdl_username:          Username that will be used to download the
                                      resources with gallery-dl.
        :param gdl_password:          Password of the related username, will be used
                                      to download the resources with gallery-dl.
        :param use_download_archive:  Record downloaded files in the download archive.
                                      This will download only files not listed in
                                      the archive file.
        :param ignore_existing_item:  Ignores the check for existing items on archive.org.
        :return:                      A dict of the downloaded posts:
                                      {path of the post's `.info.json` without the
                                      `.info.json` extension: {path of a downloaded
                                      file: its gallery-dl metadata}}
        """
        posts = collections.defaultdict(dict)

        def on_file(filepath, kwdict, page_url, post_basename):
            # Copy the metadata, gallery-dl reuses the dict for the next file
            meta = {key: value for key, value in kwdict.items()
                    if not key.startswith('_')}
            meta['webpage_url'] = page_url
            posts[post_basename][filepath] = meta

        def check_if_ia_item_exists(kwdict, post_name):
            itemname = get_itemname(kwdict.get('category'), post_name)
            item = internetarchive.get_item(itemname)
            if item.exists:
                if self.verbose:
                    print("\n:: Item already exists. Not downloading.")
                    print('Item: %s\n' % itemname)
                return True
            return False

        should_skip = None if ignore_existing_item else check_if_ia_item_exists

        gdl_opts = self.generate_gdl_options(cookie_file, proxy_url,
                                             gdl_username, gdl_password,
                                             use_download_archive)
        self.apply_gdl_options(gdl_opts)

        for url in urls:
            try:
                job = GalleryJob(url, on_file=on_file,
                                 should_skip=should_skip)
            except gdl_exception.NoExtractorError:
                self.logger.warning('URL "%s" is not supported by gallery-dl. '
                                    'Skipping.' % url)
                continue
            job.run()

        self.logger.debug(
            'Posts obtained from urls (%s): %s' % (urls, list(posts)))

        return dict(posts)

    def generate_gdl_options(self,
                             cookie_file=None,
                             proxy_url=None,
                             gdl_username=None,
                             gdl_password=None,
                             use_download_archive=False):
        """
        Generate a dictionary that contains options that will be used
        by gallery-dl, keyed by their gallery-dl config section.

        :param cookie_file:           A cookie file for gallery-dl.
        :param proxy_url:             A proxy url for gallery-dl.
        :param gdl_username:          Username that will be used to download the
                                      resources with gallery-dl.
        :param gdl_password:          Password of the related username, will be
                                      used to download the resources with
                                      gallery-dl.
        :param use_download_archive:  Record downloaded files in the download archive.
                                      This will download only files not listed in
                                      the archive file.
        :return:                      A dictionary that contains options that will
                                      be used by gallery-dl.
        """
        extractor_opts = {
            'base-directory': self.dir_path['downloads'],
            'skip': True,
            'url-metadata': 'file_url',
        }

        # Name files `{id}.{extension}`, or `{id}_{num}.{extension}` when a
        # post has several files, e.g. `{id}_1.jpg` (see `get_filename`)
        extractor_opts['filename'] = (self.output_template or
                                      '{_galup_filename}.{extension}')

        # Write gallery-dl's metadata of each post to `{id}.info.json`
        extractor_opts['postprocessors'] = [{
            'name': 'metadata',
            'event': 'post',
            'filename': '{_galup_post}.info.json',
        }]

        if cookie_file is not None:
            extractor_opts['cookies'] = cookie_file

        if proxy_url is not None:
            extractor_opts['proxy'] = proxy_url

        if gdl_username is not None:
            extractor_opts['username'] = gdl_username

        if gdl_password is not None:
            extractor_opts['password'] = gdl_password

        if use_download_archive:
            extractor_opts['archive'] = os.path.join(self.dir_path['root'],
                                                     '.gallerydlarchive')

        return {
            'extractor': extractor_opts,
            'downloader': {
                'part': True,
                'retries': 9001,
            },
            'output': {
                'mode': 'auto' if self.verbose else 'null',
                'skip': self.verbose,
            },
        }

    @staticmethod
    def apply_gdl_options(gdl_opts):
        """
        Load the user's gallery-dl configuration files, then apply the options
        generated by `generate_gdl_options` on top of them.

        :param gdl_opts:  A dictionary returned by `generate_gdl_options`.
        """
        gdl_config.clear()
        gdl_config.load()
        for section, options in gdl_opts.items():
            for key, value in options.items():
                if key == 'postprocessors':
                    # Keep the user's own post processors
                    value = list(gdl_config.get((section,), key) or ()) + value
                gdl_config.set((section,), key, value)

    def upload_ia(self, basename, files, custom_meta=None):
        """
        Upload the downloaded files of a post to a single archive.org item.

        :param basename:     Path of the post's `.info.json` file without its
                             `.info.json` extension.
        :param files:        A list of tuples of (path of a downloaded file of
                             the post, its gallery-dl metadata).
        :param custom_meta:  A custom meta, will be used by internetarchive
                             library when uploading to archive.org.
        :return:             A tuple containing item name and metadata used
                             when uploading to archive.org.
        """
        for filepath, _ in files:
            # Exit if download did not complete, don't upload .part files
            # to IA
            if os.path.exists(filepath + '.part'):
                msg = ('Download incomplete, please re-run or delete the '
                       '.part files in downloads folder, exiting...')
                raise Exception(msg)
            if not os.path.isfile(filepath):
                raise Exception('Downloaded file "%s" is missing, please '
                                're-run, exiting...' % filepath)

        # Build the item metadata from its main file: a video if there is
        # one, otherwise an image, e.g. the slides of a TikTok slideshow
        # rather than its background music, but never the thumbnail.
        def file_priority(file):
            extension = str(file[1].get('extension') or '').lower()
            if file[1].get('type') == 'thumbnail':
                return 3
            if extension in VIDEO_EXTENSIONS:
                return 0
            if extension in AUDIO_EXTENSIONS:
                return 2
            return 1

        file_meta = min(files, key=file_priority)[1]

        itemname = get_itemname(file_meta.get('category'), basename)
        metadata = self.create_archive_org_metadata_from_gallerydl_meta(
            file_meta, os.path.basename(basename))

        # Upload all files of the post and its .info.json
        files_to_upload = [filepath for filepath, _ in files]
        if os.path.isfile(basename + '.info.json'):
            files_to_upload.append(basename + '.info.json')

        # Upload the item to the Internet Archive
        item = internetarchive.get_item(itemname)

        if custom_meta:
            metadata.update(custom_meta)

        # Parse internetarchive configuration file.
        parsed_ia_s3_config = parse_config_file(self.ia_config_path)[2]['s3']
        s3_access_key = parsed_ia_s3_config['access']
        s3_secret_key = parsed_ia_s3_config['secret']

        if None in {s3_access_key, s3_secret_key}:
            msg = ('`internetarchive` configuration file is not configured'
                   ' properly.')

            self.logger.error(msg)
            if self.verbose:
                print(msg)
            raise Exception(msg)

        item.upload(files_to_upload, metadata=metadata, retries=9001,
                    request_kwargs=dict(timeout=(9001, 9001)), delete=True,
                    verbose=self.verbose, access_key=s3_access_key,
                    secret_key=s3_secret_key)

        return itemname, metadata

    def archive_urls(self, urls, custom_meta=None,
                     cookie_file=None, proxy=None,
                     gdl_username=None, gdl_password=None,
                     use_download_archive=False,
                     ignore_existing_item=False):
        """
        Download and upload files from gallery-dl supported sites to
        archive.org

        :param urls:                  List of url that will be downloaded and uploaded
                                      to archive.org
        :param custom_meta:           A custom metadata that will be used when
                                      uploading the file with archive.org.
        :param cookie_file:           A cookie file for gallery-dl.
        :param proxy:                 A proxy url for gallery-dl.
        :param gdl_username:          Username that will be used to download the
                                      resources with gallery-dl.
        :param gdl_password:          Password of the related username, will be used
                                      to download the resources with gallery-dl.
        :param use_download_archive:  Record downloaded files in the download archive.
                                      This will download only files not listed in
                                      the archive file.
        :param ignore_existing_item:  Ignores the check for existing items on archive.org.
        :return:                      Tuple containing identifier and metadata of the
                                      file that has been uploaded to archive.org.
        """
        posts = self.get_resource_basenames(
            urls, cookie_file, proxy, gdl_username, gdl_password,
            use_download_archive, ignore_existing_item)
        for basename, files in sorted(posts.items()):
            identifier, meta = self.upload_ia(basename, list(files.items()),
                                              custom_meta)
            yield identifier, meta

    @staticmethod
    def determine_media_type(file_meta, url):
        """
        Determine the archive.org mediatype and collection of a file.

        :param file_meta:  gallery-dl metadata of the file.
        :param url:        URL the file was downloaded from.
        :return:           Tuple of (mediatype, collection).
        """
        extension = str(file_meta.get('extension') or '').lower()
        if (extension in AUDIO_EXTENSIONS or
                urlparse(url).netloc == 'soundcloud.com'):
            return 'audio', 'opensource_audio'
        if extension in VIDEO_EXTENSIONS:
            return 'movies', 'opensource_movies'
        return 'image', 'opensource_image'

    @staticmethod
    def determine_licenseurl(file_meta):
        """
        Determine licenseurl for a file

        :param file_meta:  gallery-dl metadata of the file.
        :return:           License url, or an empty string if unknown.
        """
        licenseurl = ''
        licenses = {
            "Creative Commons Attribution license (reuse allowed)": "https://creativecommons.org/licenses/by/3.0/",
            "Attribution-NonCommercial-ShareAlike": "https://creativecommons.org/licenses/by-nc-sa/2.0/",
            "Attribution-NonCommercial": "https://creativecommons.org/licenses/by-nc/2.0/",
            "Attribution-NonCommercial-NoDerivs": "https://creativecommons.org/licenses/by-nc-nd/2.0/",
            "Attribution": "https://creativecommons.org/licenses/by/2.0/",
            "Attribution-ShareAlike": "https://creativecommons.org/licenses/by-sa/2.0/",
            "Attribution-NoDerivs": "https://creativecommons.org/licenses/by-nd/2.0/"
        }

        license_name = file_meta.get('license')
        if isinstance(license_name, str) and license_name:
            licenseurl = licenses.get(license_name, '')

        return licenseurl

    @staticmethod
    def determine_channel(file_meta, username):
        """
        Determine the URL of the uploader's profile, like TubeUp's `channel`.

        :param file_meta:  gallery-dl metadata of the file.
        :param username:   Username of the uploader, or None if unknown.
        :return:           Profile URL, or None if unknown.
        """
        for key in ('uploader_url', 'channel_url', 'author_url', 'user_url',
                    'profile_url'):
            value = file_meta.get(key)
            if isinstance(value, str) and value.startswith('http'):
                return value

        category = file_meta.get('category')
        user = file_meta.get('user')
        if category == 'pixiv' and isinstance(user, dict) and user.get('id'):
            return 'https://www.pixiv.net/users/%s' % user['id']
        if category == 'kemono' and file_meta.get('service') and user:
            return 'https://kemono.cr/%s/user/%s' % (file_meta['service'],
                                                     user)
        blog = file_meta.get('blog')
        if category == 'tumblr' and isinstance(blog, dict) and \
                blog.get('url'):
            return blog['url']

        if username and category in CHANNEL_URLS:
            return CHANNEL_URLS[category].format(username=username)
        return None

    @staticmethod
    def _first_text(file_meta, keys, dict_keys=('name', 'username', 'nick')):
        """
        Return the first non-empty string value found under one of `keys`.
        Dict values (e.g. gallery-dl's `user` or `author`) are searched for
        the first of `dict_keys` they contain.
        """
        for key in keys:
            value = file_meta.get(key)
            if isinstance(value, dict):
                value = next((value[k] for k in dict_keys if value.get(k)),
                             None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _tags_list(value):
        if isinstance(value, str):
            return value.split()
        if isinstance(value, list):
            tags = []
            for tag in value:
                if isinstance(tag, dict):
                    # TikTok uses `title` in `challenges` and `hashtagName`
                    # in `textExtra`
                    tag = (tag.get('name') or tag.get('title') or
                           tag.get('hashtagName'))
                if isinstance(tag, str) and tag:
                    tags.append(tag)
            return tags
        return []

    @staticmethod
    def create_archive_org_metadata_from_gallerydl_meta(file_meta, basename):
        """
        Create an archive.org metadata from gallery-dl-generated metadata.

        :param file_meta:  A dict containing gallery-dl-generated metadata.
        :param basename:   Filename of the downloaded file without its
                           extension, used as a fallback title.
        :return:           A dict containing metadata to be used by
                           internetarchive library.
        """
        category = file_meta.get('category') or 'gallery-dl'
        pageurl = file_meta.get('webpage_url') or file_meta.get('file_url') or ''

        mediatype, collection = GalUp.determine_media_type(file_meta, pageurl)

        title = GalUp._first_text(file_meta, ('title', 'post_title')) or \
            '%s %s' % (category, basename)

        # Use the uploader's username rather than their display name, as it
        # is stable and unique. Extractors store it differently, e.g.
        # `author[name]` (twitter), `author[uniqueId]` (tiktok),
        # `author[handle]` (bluesky) or `user[account]` (pixiv).
        username = GalUp._first_text(
            file_meta, ('username', 'author', 'user', 'uploader', 'owner',
                        'creator', 'artist', 'blog_name'),
            dict_keys=('username', 'account', 'handle', 'uniqueId',
                       'screen_name', 'name'))
        # Some services don't tell you the uploader,
        # use our program's name in that case.
        uploader = username or 'galup'

        try:  # some files don't give an upload date
            d = datetime.fromisoformat(str(file_meta['date']))
            upload_date = d.date().isoformat()
            upload_year = upload_date[:4]
        except (KeyError, TypeError, ValueError):
            # Use current date and time as default values
            upload_date = time.strftime("%Y-%m-%d")
            upload_year = time.strftime("%Y")

        # load up tags into an IA compatible semicolon-separated string
        # example: twitter;image;
        tags_string = '%s;%s;' % (category, mediatype)

        tags = []
        for key in ('tags', 'hashtags', 'categories', 'challenges',
                    'textExtra'):
            for tag in GalUp._tags_list(file_meta.get(key)):
                if tag not in tags:
                    tags.append(tag)
        for tag in tags:
            tags_string += '%s;' % tag

        # IA's subject field has a 255 bytes length limit, so we need to truncate tags_string
        while len(tags_string.encode('utf-8')) > 255:
            tags_list = tags_string.split(';')
            tags_list.pop()
            tags_string = ';'.join(tags_list)

        # license
        licenseurl = GalUp.determine_licenseurl(file_meta)

        description_text = GalUp._first_text(
            file_meta, ('description', 'content', 'caption', 'text',
                        'desc')) or ''
        # archive.org does not display raw newlines
        description = re.sub('\r?\n', '<br>', description_text)

        metadata = dict(
            mediatype=mediatype,
            creator=uploader,
            collection=collection,
            title=title,
            description=description,
            date=upload_date,
            year=upload_year,
            subject=tags_string,
            originalurl=pageurl,
            licenseurl=licenseurl,

            # Set 'scanner' metadata pair to allow tracking of galup
            # powered uploads, per request from archive.org. This fork
            # identifies itself separately from upstream TubeUp.
            scanner='GalUp Image Video Mirroring Application {}'.format(__version__))

        # Link to the uploader's profile, like TubeUp's `channel`
        channel = GalUp.determine_channel(file_meta, username)
        if channel:
            metadata['channel'] = channel

        return metadata
