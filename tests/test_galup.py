import unittest
import os
import shutil
import json
import re
import time
import requests_mock
import glob
import logging

from datetime import datetime

from galup.GalUp import GalUp, GalleryJob, DOWNLOAD_DIR_NAME
from galup import __version__
from unittest.mock import patch


current_path = os.path.dirname(os.path.realpath(__file__))

SCANNER = 'GalUp Image Video Mirroring Application {}'.format(__version__)

TWEET_URL = 'https://x.com/example_artist/status/1700000000000000001'
TWEET_BASENAME = 'twitter_1700000000000000001_1'
TWEET_ITEMNAME = 'twitter-1700000000000000001'

TWEET_METADATA = {
    'mediatype': 'image',
    'creator': 'example_artist',
    'collection': 'opensource_image',
    'title': 'twitter %s' % TWEET_BASENAME,
    'description': ('Mountain sketch, finished today<br>'
                    'Thanks for looking! #art #mountains'),
    'date': '2023-09-08',
    'year': '2023',
    'subject': 'twitter;image;art;mountains;',
    'originalurl': TWEET_URL,
    'licenseurl': '',
    'source': 'https://pbs.twimg.com/media/F5aBcDeXYZ?format=jpg&name=orig',
    'scanner': SCANNER}


def get_testfile_path(name):
    return os.path.join(current_path, 'test_galup_files', name)


def load_tweet_meta():
    with open(get_testfile_path('%s.info.json' % TWEET_BASENAME)) as f:
        return json.load(f)


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
                     self.url)
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
                'url-metadata': 'file_url'},
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

    def test_write_info_json(self):
        basename = downloads_path('write_info_json_test')
        os.makedirs(os.path.dirname(basename), exist_ok=True)

        json_path = GalUp.write_info_json(
            basename,
            {'category': 'twitter', 'id': 1, '_private': object(),
             'date': datetime(2023, 9, 8, 12, 34, 56)},
            TWEET_URL)

        with open(json_path) as f:
            result = json.load(f)
        os.remove(json_path)

        self.assertEqual(json_path, basename + '.info.json')
        self.assertNotIn('_private', result)
        self.assertEqual(result['category'], 'twitter')
        self.assertEqual(result['webpage_url'], TWEET_URL)
        self.assertEqual(result['date'], '2023-09-08 12:34:56')

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
                         'danbooru;image;mountain;landscape;sky;')

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
        self.assertEqual(result['subject'], 'tiktok;image;fyp;china;中国人;')
        self.assertEqual(result['creator'], 'blossom_lovecn')

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

        expected_result = {downloads_path(TWEET_BASENAME)}

        self.assertEqual(expected_result, result)

        with open(downloads_path(TWEET_BASENAME + '.info.json')) as f:
            self.assertEqual(json.load(f)['webpage_url'], TWEET_URL)

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

            result = tu.upload_ia(basename)

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
                tu.upload_ia(basename)
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

        # A TikTok slideshow: two images and the background music, all
        # belonging to post 7700361800876920077
        title = 'Educational video! #fyp #中国人'
        files = {
            '7700361800876920077 %s [7686696195469609741]' % title: 'mp3',
            '7700361800876920077_01 %s [a361480546174f43]' % title: 'jpg',
            '7700361800876920077_02 %s [e9b6b741d26948b5]' % title: 'jpg',
        }
        os.makedirs(downloads_path('tiktok'), exist_ok=True)
        basenames = set()
        for name, extension in files.items():
            basename = downloads_path('tiktok', name)
            basenames.add(basename)
            with open('%s.%s' % (basename, extension), 'wb') as f:
                f.write(b'data')
            GalUp.write_info_json(
                basename,
                {'category': 'tiktok', 'id': '7700361800876920077',
                 'title': title, 'extension': extension},
                'https://www.tiktok.com/@user/photo/7700361800876920077')

        itemname = 'tiktok-7700361800876920077'
        try:
            with requests_mock.Mocker() as m, \
                    patch.object(GalUp, 'get_resource_basenames',
                                 return_value=basenames):
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

                result = list(tu.archive_urls(['https://www.tiktok.com/']))

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
        self.assertEqual(len(uploaded), 6)


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

    def on_file(self, filepath, kwdict, page_url):
        self.reported.append((filepath, kwdict['category'], page_url))

    def test_reports_downloaded_file(self):
        with requests_mock.Mocker() as m:
            m.get(self.IMAGE_URL, content=b'image data',
                  headers={'content-type': 'image/jpeg'})
            GalleryJob(self.IMAGE_URL, on_file=self.on_file).run()

        self.assertEqual(len(self.reported), 1)
        filepath, category, page_url = self.reported[0]
        self.assertTrue(filepath.startswith(downloads_path('directlink')))
        self.assertTrue(filepath.endswith('galleryjob_test.jpg'))
        self.assertTrue(os.path.isfile(filepath))
        self.assertEqual(category, 'directlink')
        self.assertEqual(page_url, self.IMAGE_URL)

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
