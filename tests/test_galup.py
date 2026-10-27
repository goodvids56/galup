import unittest
import os
import shutil
import json
import re
import time
import requests_mock
import glob
import logging


from galup.GalUp import GalUp, GalleryJob, DOWNLOAD_DIR_NAME
from galup.utils import get_filename
from galup import __version__
from unittest.mock import patch
from gallery_dl import extractor as gdl_extractor, text
from gallery_dl.extractor.common import Extractor, Message


current_path = os.path.dirname(os.path.realpath(__file__))

SCANNER = 'GalUp Image Video Mirroring Application {}'.format(__version__)

TWEET_URL = 'https://x.com/example_artist/status/1700000000000000001'
# gallery-dl metadata of the tweet's image
TWEET_GDL_META = 'twitter_1700000000000000001_1.info.json'
TWEET_BASENAME = '1700000000000000001'
TWEET_ITEMNAME = 'Twitter-1700000000000000001'

TWEET_METADATA = {
    'mediatype': 'image',
    'creator': 'example_artist',
    'collection': 'opensource_image',
    'title': 'Twitter #%s' % TWEET_BASENAME,
    'description': ('Mountain sketch, finished today<br>'
                    'Thanks for looking! #art #mountains'),
    'date': '2023-09-08',
    'year': '2023',
    'subject': 'Twitter;image;art;mountains;',
    'originalurl': TWEET_URL,
    'licenseurl': '',
    'scanner': SCANNER,
    'channel': 'https://x.com/example_artist'}


def get_testfile_path(name):
    return os.path.join(current_path, 'test_galup_files', name)


def load_tweet_meta():
    with open(get_testfile_path(TWEET_GDL_META)) as f:
        return json.load(f)


def tweet_files():
    """Files of the tweet as reported by `get_resource_basenames`"""
    meta = load_tweet_meta()
    return [(downloads_path(TWEET_BASENAME + '.jpg'), meta)]


def downloads_path(*names):
    return os.path.join(current_path, 'test_galup_rootdir', 'downloads',
                        *names)


def mock_upload_response_by_basename(m, ia_id, basename):
    files_to_upload = glob.glob(glob.escape(basename) + '.*')

    for file_path in files_to_upload:
        filename = os.path.basename(file_path)
        m.put('https://s3.us.archive.org/%s/%s' % (ia_id, filename),
              content=b'',
              headers={'content-type': 'text/plain'})


def copy_testfiles_to_galup_rootdir_test():
    # Copy testfiles to rootdir path of GalUp.
    # This method was created because after the uploading done by
    # internetarchive library, it deletes the files that has been uploaded.
    testfiles_dir = os.path.join(current_path, 'test_galup_files',
                                 'files_for_upload_and_download_tests')

    for filepath in os.listdir(testfiles_dir):
        shutil.copy(os.path.join(testfiles_dir, filepath),
                    downloads_path(filepath))


class FakePathFormat(object):
    def __init__(self, realpath, kwdict):
        self.realpath = realpath
        self.kwdict = kwdict


# Hijacked GalleryJob class so we don't make any real download requests.
# Instead of downloading, it reports the test file that is already in the
# downloads directory, the same way the real job reports finished downloads.
class MockGalleryJob(object):
    def __init__(self, url, parent=None, on_file=None, should_skip=None):
        print("MockGalleryJob: Mocked gallery-dl extraction of URL %s" % url)

        # make sure the url is one we expect to get. If the tests URL ever
        # change for some reason, this will fail, and we can add new cases
        # if needed.
        if url != TWEET_URL:
            raise ValueError("unexpected URL")

        self.url = url
        self.on_file = on_file

    def run(self):
        kwdict = load_tweet_meta()
        del kwdict['webpage_url']
        self.on_file(downloads_path(TWEET_BASENAME + '.jpg'), kwdict,
                     self.url, downloads_path(TWEET_BASENAME))
        return 0


@patch("galup.GalUp.GalleryJob", MockGalleryJob)
class GalUpTests(unittest.TestCase):

    def setUp(self):
        self.tu = GalUp()
        self.maxDiff = 999999999

    def test_set_dir_path(self):
        root_path = os.path.join(
            current_path, '.directory_for_galup_set_dir_path_test')
        dir_paths_dict = dict(root=root_path,
                              downloads=os.path.join(root_path,
                                                     DOWNLOAD_DIR_NAME))

        self.tu.dir_path = root_path
        self.assertEqual(self.tu.dir_path, dir_paths_dict)

        # Make sure that other directories are created as well
        self.assertTrue(os.path.exists(dir_paths_dict['downloads']))

        # Clean the test directory
        shutil.rmtree(root_path, ignore_errors=True)

    def test_galup_attribute_logger_when_quiet_mode(self):
        # self.tu is already `GalUp` instance with quiet mode, so we don't
        # create a new instance here.
        self.assertIsInstance(self.tu.logger, logging.Logger)
        self.assertEqual(self.tu.logger.level, logging.ERROR)

    def test_galup_attribute_logger_when_verbose_mode(self):
        tu = GalUp(verbose=True)
        self.assertIsInstance(tu.logger, logging.Logger)

    def test_determine_media_type(self):
        self.assertEqual(
            self.tu.determine_media_type({'extension': 'jpg'},
                                         'https://example.com/post/1'),
            ('image', 'opensource_image'))
        self.assertEqual(
            self.tu.determine_media_type({'extension': 'MP4'},
                                         'https://example.com/post/1'),
            ('movies', 'opensource_movies'))
        self.assertEqual(
            self.tu.determine_media_type({'extension': 'flac'},
                                         'https://example.com/post/1'),
            ('audio', 'opensource_audio'))
        self.assertEqual(
            self.tu.determine_media_type({}, 'https://soundcloud.com/testurl'),
            ('audio', 'opensource_audio'))

    def test_gallery_job_is_a_gallery_dl_download_job(self):
        # The class patch above only replaces the name used by GalUp.py
        from gallery_dl.job import DownloadJob
        self.assertTrue(issubclass(GalleryJob, DownloadJob))

    def test_generate_gdl_options(self):
        result = self.tu.generate_gdl_options()

        expected_result = {
            'extractor': {
                'base-directory': self.tu.dir_path['downloads'],
                'skip': True,
                'url-metadata': 'file_url',
                'filename': '{_galup_filename}.{extension}',
                'postprocessors': [{
                    'name': 'metadata',
                    'event': 'post',
                    'filename': '{_galup_post}.info.json'}],
                'tiktok': {'user': {'include': 'posts'}}},
            'downloader': {
                'part': True,
                'retries': 9001},
            'output': {
                'mode': 'null',
                'skip': False}}

        self.assertEqual(result, expected_result)

    def test_generate_gdl_options_with_download_archive(self):
        result = self.tu.generate_gdl_options(use_download_archive=True)

        self.assertEqual(result['extractor']['archive'],
                         os.path.join(self.tu.dir_path['root'],
                                      '.gallerydlarchive'))

    def test_generate_gdl_options_with_proxy(self):
        result = self.tu.generate_gdl_options(
            proxy_url='http://proxytest.com:8080')

        self.assertEqual(result['extractor']['proxy'],
                         'http://proxytest.com:8080')

    def test_generate_gdl_options_with_cookies(self):
        result = self.tu.generate_gdl_options(cookie_file='cookies.txt')

        self.assertEqual(result['extractor']['cookies'], 'cookies.txt')

    def test_generate_gdl_options_with_gdl_account(self):
        result = self.tu.generate_gdl_options(
            gdl_username='testUsername', gdl_password='testPassword')

        self.assertEqual(result['extractor']['username'], 'testUsername')
        self.assertEqual(result['extractor']['password'], 'testPassword')

    def test_generate_gdl_options_with_output_template(self):
        tu = GalUp(output_template='{category}_{id}.{extension}')
        result = tu.generate_gdl_options()

        self.assertEqual(result['extractor']['filename'],
                         '{category}_{id}.{extension}')

    def test_generate_gdl_options_with_verbose_mode(self):
        tu = GalUp(verbose=True)
        result = tu.generate_gdl_options()

        self.assertEqual(result['output'], {'mode': 'auto', 'skip': True})

    def test_create_archive_org_metadata_from_gallerydl_meta(self):
        result = GalUp.create_archive_org_metadata_from_gallerydl_meta(
            load_tweet_meta(), TWEET_BASENAME)

        self.assertEqual(TWEET_METADATA, result)

    def test_create_archive_org_metadata_from_gallerydl_meta_with_title(self):
        vid_meta = load_tweet_meta()
        vid_meta['title'] = 'Mountain sketch'

        result = GalUp.create_archive_org_metadata_from_gallerydl_meta(
            vid_meta, TWEET_BASENAME)

        self.assertEqual(result['title'], 'Mountain sketch')

    def test_create_archive_org_metadata_from_gallerydl_meta_no_uploader(self):
        vid_meta = load_tweet_meta()
        del vid_meta['author']
        del vid_meta['user']

        result = GalUp.create_archive_org_metadata_from_gallerydl_meta(
            vid_meta, TWEET_BASENAME)

        self.assertEqual(result['creator'], 'galup')

    def test_create_archive_org_metadata_from_gallerydl_meta_string_uploader(self):
        vid_meta = load_tweet_meta()
        del vid_meta['author']
        vid_meta['user'] = 'someone'

        result = GalUp.create_archive_org_metadata_from_gallerydl_meta(
            vid_meta, TWEET_BASENAME)

        self.assertEqual(result['creator'], 'someone')

    def test_create_archive_org_metadata_from_gallerydl_meta_username(self):
        metas = [
            ('tiktok', {'author': {'uniqueId': 'blossom_lovecn',
                                   'nickname': 'Blossom'},
                        'user': 'blossom_lovecn'}),
            ('bluesky', {'author': {'did': 'did:plc:abc',
                                    'handle': 'someone.bsky.social',
                                    'displayName': 'Someone'}}),
            ('pixiv', {'user': {'id': 1, 'name': 'Display Name',
                                'account': 'account_name'}}),
            ('instagram', {'username': 'insta_user', 'fullname': 'Insta',
                           'owner_id': '123'}),
            ('kemono', {'user': '12345', 'username': 'creator'}),
        ]
        expected = ['blossom_lovecn', 'someone.bsky.social', 'account_name',
                    'insta_user', 'creator']

        result = [
            GalUp.create_archive_org_metadata_from_gallerydl_meta(
                dict(meta, category=category), 'x')['creator']
            for category, meta in metas]

        self.assertEqual(result, expected)

    def test_create_archive_org_metadata_from_gallerydl_meta_channel(self):
        metas = [
            {'category': 'tiktok', 'user': 'blossom_lovecn',
             'author': {'uniqueId': 'blossom_lovecn'}},
            {'category': 'bluesky',
             'author': {'handle': 'someone.bsky.social'}},
            {'category': 'pixiv', 'user': {'id': 42, 'account': 'acc'}},
            {'category': 'kemono', 'service': 'patreon', 'user': '12345',
             'username': 'creator'},
            {'category': 'tumblr', 'blog_name': 'art',
             'blog': {'name': 'art', 'url': 'https://art.tumblr.com/'}},
            {'category': 'bellazon', 'author': 'someone',
             'author_url': 'https://www.bellazon.com/main/profile/1-someone/'},
        ]
        expected = [
            'https://www.tiktok.com/@blossom_lovecn',
            'https://bsky.app/profile/someone.bsky.social',
            'https://www.pixiv.net/users/42',
            'https://kemono.cr/patreon/user/12345',
            'https://art.tumblr.com/',
            'https://www.bellazon.com/main/profile/1-someone/',
        ]

        result = [
            GalUp.create_archive_org_metadata_from_gallerydl_meta(
                meta, 'x').get('channel')
            for meta in metas]

        self.assertEqual(result, expected)

    def test_create_archive_org_metadata_from_gallerydl_meta_no_channel(self):
        result = GalUp.create_archive_org_metadata_from_gallerydl_meta(
            {'category': 'directlink'}, 'x')

        self.assertNotIn('channel', result)

    def test_create_archive_org_metadata_from_gallerydl_meta_no_date(self):
        vid_meta = load_tweet_meta()
        del vid_meta['date']

        result = GalUp.create_archive_org_metadata_from_gallerydl_meta(
            vid_meta, TWEET_BASENAME)

        self.assertEqual(result['date'], time.strftime("%Y-%m-%d"))
        self.assertEqual(result['year'], time.strftime("%Y"))

    def test_create_archive_org_metadata_from_gallerydl_meta_no_description(self):
        vid_meta = load_tweet_meta()
        vid_meta['content'] = None

        result = GalUp.create_archive_org_metadata_from_gallerydl_meta(
            vid_meta, TWEET_BASENAME)

        self.assertEqual(result['description'], '')

    def test_create_archive_org_metadata_from_gallerydl_meta_string_tags(self):
        vid_meta = load_tweet_meta()
        del vid_meta['hashtags']
        vid_meta['category'] = 'danbooru'
        vid_meta['tags'] = 'mountain landscape sky'

        result = GalUp.create_archive_org_metadata_from_gallerydl_meta(
            vid_meta, TWEET_BASENAME)

        self.assertEqual(result['subject'],
                         'Danbooru;image;mountain;landscape;sky;')

    def test_create_archive_org_metadata_from_gallerydl_meta_tiktok(self):
        tiktok_meta = {
            'category': 'tiktok',
            'id': '7700361800876920077',
            'desc': 'All love! #fyp #china #中国人',
            'user': 'blossom_lovecn',
            'author': {'uniqueId': 'blossom_lovecn'},
            'extension': 'jpg',
            'challenges': [{'id': '1', 'title': 'fyp'},
                           {'id': '2', 'title': 'china'}],
            'textExtra': [{'hashtagName': 'fyp'},
                          {'hashtagName': 'china'},
                          {'hashtagName': '中国人'},
                          {'hashtagName': '', 'userUniqueId': 'someone'}],
        }

        result = GalUp.create_archive_org_metadata_from_gallerydl_meta(
            tiktok_meta, 'x')

        self.assertEqual(result['description'], 'All love! #fyp #china #中国人')
        self.assertEqual(result['subject'], 'TikTok;image;fyp;china;中国人;')
        self.assertEqual(result['creator'], 'blossom_lovecn')

    def test_create_archive_org_metadata_from_gallerydl_meta_video_tag(self):
        vid_meta = load_tweet_meta()
        vid_meta['extension'] = 'mp4'

        result = GalUp.create_archive_org_metadata_from_gallerydl_meta(
            vid_meta, TWEET_BASENAME)

        self.assertEqual(result['mediatype'], 'movies')
        self.assertTrue(result['subject'].startswith('Twitter;video;'))

    def test_create_archive_org_metadata_from_gallerydl_meta_mass_of_tags(self):
        vid_meta = load_tweet_meta()
        vid_meta['tags'] = [f't{i}' for i in range(0, 300)]

        result = GalUp.create_archive_org_metadata_from_gallerydl_meta(
            vid_meta, TWEET_BASENAME)

        self.assertLessEqual(len(result['subject'].encode(encoding='utf-8')),
                             255, msg='tags_string not truncated to <= 255 bytes')

    def test_get_resource_basenames(self):
        tu = GalUp(dir_path=os.path.join(current_path,
                                         'test_galup_rootdir'))

        copy_testfiles_to_galup_rootdir_test()

        with patch.object(GalUp, 'apply_gdl_options'):
            result = tu.get_resource_basenames([TWEET_URL],
                                               ignore_existing_item=True)

        self.assertEqual(result, {
            downloads_path(TWEET_BASENAME): dict(tweet_files())})

    def test_upload_ia(self):
        tu = GalUp(dir_path=os.path.join(current_path,
                                         'test_galup_rootdir'),
                   # Use custom ia configuration file so we don't need
                   # to login with username and password.
                   ia_config_path=get_testfile_path('ia_config_for_test.ini'))

        basename = downloads_path(TWEET_BASENAME)

        copy_testfiles_to_galup_rootdir_test()

        # A file whose name merely starts with the basename must not be
        # uploaded as part of this item.
        other_file = downloads_path(TWEET_BASENAME + '0.jpg')
        with open(other_file, 'wb') as f:
            f.write(b'not part of this item')

        with requests_mock.Mocker() as m:
            # Mock the request to s3.us.archive.org, so it will responds
            # a custom json. `internetarchive` library sends GET request to
            # that url to check that we don't violate the upload limit.
            m.get('https://s3.us.archive.org',
                  content=b'{"over_limit": 0}',
                  headers={'content-type': 'application/json'})

            m.get('https://archive.org/metadata/%s' % TWEET_ITEMNAME,
                  content=b'{}',
                  headers={'content-type': 'application/json'})

            # Mock the PUT requests for internetarchive urls that defined
            # in mock_upload_response_by_basename(), so this test
            # doesn't perform upload to the real archive.org server.
            mock_upload_response_by_basename(m, TWEET_ITEMNAME, basename)

            result = tu.upload_ia(basename, tweet_files())

        self.assertEqual((TWEET_ITEMNAME, TWEET_METADATA), result)
        self.assertTrue(os.path.exists(other_file))
        os.remove(other_file)

    def test_upload_ia_incomplete_download(self):
        tu = GalUp(dir_path=os.path.join(current_path,
                                         'test_galup_rootdir'),
                   ia_config_path=get_testfile_path('ia_config_for_test.ini'))

        basename = downloads_path(TWEET_BASENAME)

        copy_testfiles_to_galup_rootdir_test()
        part_file = basename + '.jpg.part'
        with open(part_file, 'wb'):
            pass

        try:
            with self.assertRaisesRegex(Exception, 'Download incomplete'):
                tu.upload_ia(basename, tweet_files())
        finally:
            os.remove(part_file)

    def test_archive_urls(self):
        tu = GalUp(dir_path=os.path.join(current_path,
                                         'test_galup_rootdir'),
                   ia_config_path=get_testfile_path('ia_config_for_test.ini'))

        basename = downloads_path(TWEET_BASENAME)

        copy_testfiles_to_galup_rootdir_test()

        with requests_mock.Mocker() as m, \
                patch.object(GalUp, 'apply_gdl_options'):
            # Mock the request to s3.us.archive.org, so it will responds
            # a custom json. `internetarchive` library sends GET request to
            # that url to check that we don't violate the upload limit.
            m.get('https://s3.us.archive.org',
                  content=b'{"over_limit": 0}',
                  headers={'content-type': 'application/json'})

            # The item doesn't exist yet, both for the existence check done
            # before downloading and for the upload.
            m.get('https://archive.org/metadata/%s' % TWEET_ITEMNAME,
                  content=b'{}',
                  headers={'content-type': 'application/json'})

            # Mock the PUT requests for internetarchive urls that defined
            # in mock_upload_response_by_basename(), so this test
            # doesn't perform upload to the real archive.org server.
            mock_upload_response_by_basename(m, TWEET_ITEMNAME, basename)

            result = list(tu.archive_urls([TWEET_URL]))

        self.assertEqual([(TWEET_ITEMNAME, TWEET_METADATA)], result)

    def test_archive_urls_groups_files_of_a_post(self):
        tu = GalUp(dir_path=os.path.join(current_path,
                                         'test_galup_rootdir'),
                   ia_config_path=get_testfile_path('ia_config_for_test.ini'))
        page_url = 'https://www.tiktok.com/@user/photo/7700361800876920077'
        post_dir = downloads_path('tiktok', 'user')

        # A TikTok slideshow: two images and the background music
        class SlideshowJob(object):
            def __init__(self, url, on_file=None, should_skip=None):
                self.on_file = on_file

            def run(self):
                os.makedirs(post_dir, exist_ok=True)
                post = {'category': 'tiktok', 'id': '7700361800876920077',
                        'title': 'Educational video! #fyp #中国人'}
                # Written by gallery-dl's metadata post processor
                post_basename = os.path.join(post_dir, post['id'])
                with open(post_basename + '.info.json', 'w') as f:
                    json.dump(post, f)
                for num, extension in ((1, 'jpg'), (2, 'jpg'), (0, 'mp3'),
                                       (None, 'jpg')):
                    kwdict = dict(post, num=num, extension=extension)
                    name = get_filename(kwdict)
                    if num is None:
                        # The slideshow's thumbnail
                        kwdict['type'] = 'thumbnail'
                        name += '.thumbnail'
                    filepath = os.path.join(post_dir, '%s.%s' % (
                        name, extension))
                    with open(filepath, 'wb') as f:
                        f.write(b'data')
                    self.on_file(filepath, kwdict, page_url, post_basename)

        itemname = 'TikTok-7700361800876920077'
        try:
            with requests_mock.Mocker() as m, \
                    patch('galup.GalUp.GalleryJob', SlideshowJob), \
                    patch.object(GalUp, 'apply_gdl_options'):
                m.get('https://s3.us.archive.org',
                      content=b'{"over_limit": 0}',
                      headers={'content-type': 'application/json'})
                m.get('https://archive.org/metadata/%s' % itemname,
                      content=b'{}',
                      headers={'content-type': 'application/json'})
                m.put(re.compile(r'https://s3\.us\.archive\.org/%s/'
                                 % itemname),
                      content=b'',
                      headers={'content-type': 'text/plain'})

                result = list(tu.archive_urls([page_url],
                                              ignore_existing_item=True))

                uploaded = sorted(
                    os.path.basename(request.path)
                    for request in m.request_history
                    if request.method == 'PUT')
        finally:
            shutil.rmtree(downloads_path('tiktok'), ignore_errors=True)

        self.assertEqual(len(result), 1)
        identifier, meta = result[0]
        self.assertEqual(identifier, itemname)
        # The images decide the mediatype, not the background music
        self.assertEqual(meta['mediatype'], 'image')
        self.assertEqual(meta['title'], 'Educational video! #fyp #中国人')
        self.assertEqual(uploaded, [
            '7700361800876920077.info.json', '7700361800876920077.mp3',
            '7700361800876920077.thumbnail.jpg', '7700361800876920077_1.jpg',
            '7700361800876920077_2.jpg'])


class FakeSiteExtractor(Extractor):
    """A gallery-dl extractor for two posts with two images each"""
    category = 'galuptest'
    subcategory = 'user'
    directory_fmt = ('{category}', '{user}')
    pattern = r'galuptest:user'

    def items(self):
        for post_id in ('101', '102'):
            post = {'id': post_id, 'user': 'someone',
                    'title': 'Post %s' % post_id}
            yield Message.Directory, '', post
            for num in (1, 2):
                url = 'https://example.org/%s/%d.jpg' % (post_id, num)
                file = dict(post, num=num)
                text.nameext_from_url(url, file)
                yield Message.Url, url, file


gdl_extractor.add(FakeSiteExtractor)


class FakeThumbnailExtractor(Extractor):
    """A gallery-dl extractor for posts with a thumbnail"""
    category = 'galupthumbs'
    subcategory = 'user'
    directory_fmt = ('{category}', '{user}')
    pattern = r'galupthumbs:user'

    def items(self):
        posts = (
            # A video
            ('201', ['https://example.org/201/video.mp4']),
            # A single image, which is its own thumbnail
            ('202', ['https://example.org/202/image.jpg']),
            # Several images
            ('203', ['https://example.org/203/1.jpg',
                     'https://example.org/203/2.jpg']),
        )
        for post_id, urls in posts:
            post = {'id': post_id, 'user': 'someone',
                    'thumbnail': 'https://example.org/%s/thumb.jpg' % post_id}
            yield Message.Directory, '', post
            for num, url in enumerate(urls, 1):
                file = dict(post, num=num, count=len(urls))
                text.nameext_from_url(url, file)
                yield Message.Url, url, file


gdl_extractor.add(FakeThumbnailExtractor)


class GalleryJobTests(unittest.TestCase):
    """Run the real gallery-dl machinery against a mocked direct link."""

    IMAGE_URL = 'https://example.org/media/galleryjob_test.jpg'

    def setUp(self):
        self.tu = GalUp(dir_path=os.path.join(current_path,
                                              'test_galup_rootdir'))
        self.tu.apply_gdl_options(self.tu.generate_gdl_options())
        self.reported = []

    def tearDown(self):
        shutil.rmtree(downloads_path('directlink'), ignore_errors=True)
        shutil.rmtree(downloads_path('galuptest'), ignore_errors=True)
        shutil.rmtree(downloads_path('galupthumbs'), ignore_errors=True)

    def on_file(self, filepath, kwdict, page_url, post_basename):
        self.reported.append((filepath, kwdict['category'], page_url,
                              post_basename))

    def test_tiktok_profile_skips_avatar(self):
        extr = gdl_extractor.find('https://www.tiktok.com/@someone')
        extr.initialize()
        queued = [url for _, url, _ in extr.items()]

        self.assertEqual(queued, ['https://www.tiktok.com/@someone/posts'])

    def test_apply_gdl_options_keeps_user_subsection_options(self):
        from gallery_dl import config as gdl_config
        with patch.object(gdl_config, 'load',
                          lambda: gdl_config.set(('extractor', 'tiktok'),
                                                 'cookies', 'cookies.txt')):
            self.tu.apply_gdl_options(self.tu.generate_gdl_options())

        self.assertEqual(gdl_config.get(('extractor', 'tiktok'), 'cookies'),
                         'cookies.txt')
        self.assertEqual(
            gdl_config.get(('extractor', 'tiktok', 'user'), 'include'),
            'posts')

    def test_reports_downloaded_file(self):
        with requests_mock.Mocker() as m:
            m.get(self.IMAGE_URL, content=b'image data',
                  headers={'content-type': 'image/jpeg'})
            GalleryJob(self.IMAGE_URL, on_file=self.on_file).run()

        self.assertEqual(len(self.reported), 1)
        filepath, category, page_url, post_basename = self.reported[0]
        self.assertTrue(filepath.startswith(downloads_path('directlink')))
        self.assertTrue(filepath.endswith('galleryjob_test.jpg'))
        self.assertTrue(os.path.isfile(filepath))
        self.assertEqual(category, 'directlink')
        self.assertEqual(page_url, self.IMAGE_URL)

        # gallery-dl's metadata post processor wrote the post's .info.json
        self.assertEqual(post_basename,
                         os.path.join(os.path.dirname(filepath),
                                      'galleryjob_test'))
        with open(post_basename + '.info.json') as f:
            post_meta = json.load(f)
        self.assertEqual(post_meta['category'], 'directlink')
        self.assertNotIn('_galup_post', post_meta)

    def test_should_skip_prevents_download(self):
        checked = []

        def should_skip(kwdict, basename):
            checked.append(basename)
            return True

        with requests_mock.Mocker() as m:
            GalleryJob(self.IMAGE_URL, on_file=self.on_file,
                       should_skip=should_skip).run()
            self.assertEqual(m.call_count, 0)

        self.assertEqual(len(checked), 1)
        self.assertTrue(checked[0].endswith('galleryjob_test'))
        self.assertEqual(self.reported, [])

    def test_names_files_and_info_json_by_post(self):
        with requests_mock.Mocker() as m:
            m.get(re.compile(r'https://example\.org/.*'), content=b'image',
                  headers={'content-type': 'image/jpeg'})
            GalleryJob('galuptest:user', on_file=self.on_file).run()

        user_dir = downloads_path('galuptest', 'someone')
        self.assertEqual(sorted(os.listdir(user_dir)), [
            '101.info.json', '101_1.jpg', '101_2.jpg',
            '102.info.json', '102_1.jpg', '102_2.jpg'])
        self.assertEqual(
            [(os.path.basename(filepath), post_basename)
             for filepath, _, _, post_basename in self.reported],
            [('101_1.jpg', os.path.join(user_dir, '101')),
             ('101_2.jpg', os.path.join(user_dir, '101')),
             ('102_1.jpg', os.path.join(user_dir, '102')),
             ('102_2.jpg', os.path.join(user_dir, '102'))])

        # One .info.json per post, with gallery-dl's metadata of the post
        with open(os.path.join(user_dir, '102.info.json')) as f:
            self.assertEqual(json.load(f), {
                'id': '102', 'user': 'someone', 'title': 'Post 102',
                'category': 'galuptest', 'subcategory': 'user'})

    def test_downloads_thumbnail_of_post(self):
        with requests_mock.Mocker() as m:
            m.get(re.compile(r'https://example\.org/.*\.mp4'),
                  content=b'video', headers={'content-type': 'video/mp4'})
            m.get(re.compile(r'https://example\.org/.*\.jpg'),
                  content=b'image', headers={'content-type': 'image/jpeg'})
            GalleryJob('galupthumbs:user', on_file=self.on_file).run()

            thumbnails = sorted(request.path for request in m.request_history
                                if request.path.endswith('/thumb.jpg'))

        user_dir = downloads_path('galupthumbs', 'someone')
        self.assertEqual(sorted(os.listdir(user_dir)), [
            '201.info.json', '201.mp4', '201.thumbnail.jpg',
            '202.info.json', '202.jpg',
            '203.info.json', '203.thumbnail.jpg', '203_1.jpg', '203_2.jpg'])
        # The single image post isn't given a thumbnail
        self.assertEqual(thumbnails, ['/201/thumb.jpg', '/203/thumb.jpg'])

        # Thumbnails are reported as files of their post
        reported = [(os.path.basename(filepath),
                     os.path.basename(post_basename))
                    for filepath, _, _, post_basename in self.reported]
        self.assertIn(('201.thumbnail.jpg', '201'), reported)
        self.assertIn(('203.thumbnail.jpg', '203'), reported)
