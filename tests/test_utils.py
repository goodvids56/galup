import unittest
import os
from galup.utils import (sanitize_identifier, check_is_file_empty,
                         get_itemname, get_filename)


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

    def test_get_itemname(self):
        tiktok_basename = (
            '/downloads/tiktok/user/7700361800876920077 Educational! '
            '#fyp #中国人 #中国  [7686696195469609741]')
        self.assertEqual(
            get_itemname({'category': 'tiktok', 'id': '7700361800876920077'},
                         tiktok_basename),
            'tiktok-7700361800876920077')
        self.assertEqual(
            get_itemname({'category': 'twitter',
                          'tweet_id': 1700000000000000001,
                          'author': {'id': 123}},
                         '/downloads/twitter/user/1700000000000000001_1'),
            'twitter-1700000000000000001')
        self.assertEqual(
            get_itemname({'category': 'instagram', 'post_id': '31',
                          'media_id': '32'}, 'x'),
            'instagram-31')
        self.assertEqual(
            get_itemname({'category': 'boosty', 'id': 'file',
                          'post': {'id': 'abc-123'}}, 'x'),
            'boosty-abc-123')
        self.assertEqual(
            get_itemname({'category': 'bunkr', 'id': 'file',
                          'album_id': 'Xy7'}, 'x'),
            'bunkr-Xy7')
        self.assertEqual(
            get_itemname({'category': 'deviantart', 'index': 987}, 'x'),
            'deviantart-987')

    def test_get_itemname_without_post_id(self):
        self.assertEqual(
            get_itemname({'category': 'directlink'},
                         'example.org_media_image'),
            'directlink-example-org_media_image')
        self.assertEqual(
            get_itemname({'category': 'twitter', 'tweet_id': 0},
                         'avatar 2023'),
            'twitter-avatar-2023')
        self.assertEqual(get_itemname({}, 'image'), 'gallery-dl-image')
        self.assertEqual(
            len(get_itemname({'category': 'pixiv'}, 'x' * 200)), 100)

    def test_get_itemname_strips_non_ascii(self):
        itemname = get_itemname(
            {'category': 'tiktok'},
            '/downloads/tiktok/user/7700361800876920077 Educational! '
            '#fyp #中国人 #中国  [7686696195469609741]')
        self.assertEqual(
            itemname,
            'tiktok-7700361800876920077-Educational---fyp------------'
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
