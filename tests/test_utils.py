import unittest
import os
from galup.utils import (sanitize_identifier, check_is_file_empty,
                         get_itemname, get_filename, get_post_name,
                         get_platform_name, get_thumbnail_url,
                         get_subtitle_extension)


class UtilsTest(unittest.TestCase):

    def test_preserve_valid_identifiers(self):
        valid = [
            'youtube--QBwhSklJks',
            'youtube-_--M04_mN-M',
            'youtube-Xy2jZABDB40'
        ]
        clean = [sanitize_identifier(x) for x in valid]
        self.assertListEqual(valid, clean)

    def test_sanitize_bad_identifiers(self):
        bad = [
            'twitch:vod-v181464551',
            'twitch:clips-1003820974',
            'twitter:card-1192732384065708032'
        ]
        expect = [
            'twitch-vod-v181464551',
            'twitch-clips-1003820974',
            'twitter-card-1192732384065708032'
        ]
        clean = [sanitize_identifier(x) for x in bad]
        self.assertListEqual(expect, clean)

    def test_get_post_name(self):
        cases = [
            ({'category': 'tiktok', 'id': '7700361800876920077'},
             '7700361800876920077'),
            ({'category': 'twitter', 'tweet_id': 1700000000000000001,
              'author': {'id': 123}}, '1700000000000000001'),
            ({'category': 'instagram', 'post_id': '31', 'media_id': '32'},
             '31'),
            ({'category': 'boosty', 'id': 'file', 'post': {'id': 'abc-123'}},
             'abc-123'),
            ({'category': 'bunkr', 'id': 'file', 'album_id': 'Xy7'}, 'Xy7'),
            ({'category': 'deviantart', 'index': 987}, '987'),
            # No post ID
            ({'category': 'directlink', 'filename': 'image'}, 'image'),
            ({'category': 'twitter', 'tweet_id': 0, 'filename': 'avatar'},
             'avatar'),
        ]
        self.assertEqual([get_post_name(meta) for meta, _ in cases],
                         [name for _, name in cases])

        # Without a post ID or file name, posts are named after a hash of
        # their metadata
        name = get_post_name({'category': 'example', 'title': 'a'})
        self.assertEqual(len(name), 16)
        self.assertEqual(name, get_post_name({'title': 'a',
                                              'category': 'example'}))
        self.assertNotEqual(name, get_post_name({'category': 'example',
                                                 'title': 'b'}))

    def test_get_platform_name(self):
        self.assertEqual(get_platform_name('tiktok'), 'TikTok')
        self.assertEqual(get_platform_name('deviantart'), 'DeviantArt')
        self.assertEqual(get_platform_name('twitter'), 'Twitter')
        self.assertEqual(get_platform_name('pixiv'), 'pixiv')
        self.assertEqual(get_platform_name('furaffinity'), 'Fur Affinity')
        self.assertEqual(get_platform_name(None), 'gallery-dl')

    def test_get_itemname(self):
        self.assertEqual(get_itemname('tiktok', '7700361800876920077'),
                         'TikTok-7700361800876920077')
        self.assertEqual(
            get_itemname('directlink', '/downloads/example.org_media_image'),
            'Directlink-example-org_media_image')
        self.assertEqual(get_itemname(None, 'image'), 'gallery-dl-image')
        self.assertEqual(get_itemname('furaffinity', '123'),
                         'Fur-Affinity-123')
        self.assertEqual(len(get_itemname('pixiv', 'x' * 200)), 100)

    def test_get_itemname_strips_non_ascii(self):
        itemname = get_itemname(
            'tiktok',
            '7700361800876920077 Educational! #fyp #中国人 #中国  '
            '[7686696195469609741]')
        self.assertEqual(
            itemname,
            'TikTok-7700361800876920077-Educational---fyp------------'
            '7686696195469609741-')
        self.assertRegex(itemname, r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{4,100}$')

    def test_get_filename(self):
        tiktok = {'category': 'tiktok', 'id': '7700361800876920077'}
        cases = [
            # TikTok slideshow images and its background music
            (dict(tiktok, num=1), '7700361800876920077_1'),
            (dict(tiktok, num=2), '7700361800876920077_2'),
            (dict(tiktok, num=0), '7700361800876920077'),
            # TikTok video
            (tiktok, '7700361800876920077'),
            # and its subtitles
            (dict(tiktok, num=0, type='subtitle',
                  subtitle_lang_codename='eng-US'),
             '7700361800876920077.eng-US'),
            (dict(tiktok, type='subtitle', language='fra-FR'),
             '7700361800876920077.fra-FR'),
            # Twitter's `lang` of a tweet isn't the language of a subtitle
            ({'tweet_id': 17, 'num': 1, 'count': 1, 'lang': 'en'}, '17'),
            # Tweets with one and with several images
            ({'tweet_id': 17, 'num': 1, 'count': 1}, '17'),
            ({'tweet_id': 17, 'num': 3, 'count': 4}, '17_3'),
            # Manga chapters are numbered by page
            ({'chapter_id': 'c1', 'page': 5}, 'c1_5'),
            # Bunkr album files have no position but an ID of their own
            ({'album_id': 'Xy7', 'id': 'f1'}, 'Xy7_f1'),
            # Catbox album files only have their original name
            ({'album_id': 'ab', 'filename': 'cat'}, 'ab_cat'),
            # No post ID
            ({'category': 'directlink', 'filename': 'image'}, None),
        ]
        self.assertEqual([get_filename(meta) for meta, _ in cases],
                         [name for _, name in cases])

    def test_get_subtitle_extension(self):
        cases = [
            ({'subtitle_format': 'webvtt'}, 'vtt'),
            ({'subtitle_format': 'creator_caption'}, 'json'),
            ({'subtitle_format': 'SRT'}, 'srt'),
            ({'subtitle_format': ''}, None),
            ({}, None),
        ]
        self.assertEqual([get_subtitle_extension(meta) for meta, _ in cases],
                         [extension for _, extension in cases])

    def test_get_thumbnail_url(self):
        cases = [
            ({'video': {'cover': 'https://t.co/c.jpg',
                        'originCover': 'https://t.co/o.jpg'}},
             'https://t.co/o.jpg'),
            ({'imagePost': {'cover': {'imageURL': {
                'urlList': ['https://t.co/s.jpg', 'https://t.co/s2.jpg']}}}},
             'https://t.co/s.jpg'),
            ({'thumbnail': 'https://b.thumbs.redditmedia.com/x.jpg'},
             'https://b.thumbs.redditmedia.com/x.jpg'),
            # Reddit uses words for posts without a thumbnail
            ({'thumbnail': 'self'}, None),
            ({'imagePost': {'cover': {'imageURL': {'urlList': []}}}}, None),
            ({'title': 'nothing'}, None),
        ]
        self.assertEqual([get_thumbnail_url(meta) for meta, _ in cases],
                         [url for _, url in cases])

    def test_check_is_file_empty_when_file_is_empty(self):
        # Create a file for the test
        with open('testemptyfile.txt', 'w'):
            pass

        self.assertTrue(check_is_file_empty('testemptyfile.txt'))
        os.remove('testemptyfile.txt')

    def test_check_is_file_empty_when_file_is_not_empty(self):
        with open('testfilenotempty.txt', 'w') as not_empty_file:
            not_empty_file.write('just a text')

        self.assertFalse(check_is_file_empty('testfilenotempty.txt'))
        os.remove('testfilenotempty.txt')

    def test_check_is_file_empty_when_file_doesnt_exist(self):
        with self.assertRaisesRegex(
                FileNotFoundError,
                r"^Path 'file_that_doesnt_exist.txt' doesn't exist$"):
            check_is_file_empty('file_that_doesnt_exist.txt')
