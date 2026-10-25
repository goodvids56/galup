import os
import re
from collections import defaultdict


def key_value_to_dict(lst):
    """
    Convert many key:value pair strings into a python dictionary
    """
    if not isinstance(lst, list):
        lst = [lst]

    result = defaultdict(list)
    for item in lst:
        key, value = item.split(":", 1)
        assert value, f"Expected a value! for {key}"
        if result[key] and value not in result[key]:
            result[key].append(value)
        else:
            result[key] = [value]

    # Convert single-item lists back to strings for non-list values
    return {k: v if len(v) > 1 else v[0] for k, v in result.items()}


def sanitize_identifier(identifier, replacement='-'):
    # archive.org identifiers may only contain ASCII letters, digits, '_' and
    # '-' ('.' is allowed too but kept out for consistency); `\w` alone would
    # also match non-ASCII letters such as Chinese characters
    return re.sub(r'[^A-Za-z0-9_-]', replacement, identifier)


# gallery-dl metadata keys holding the ID of the post a file belongs to, in
# order of preference. Extractors name it differently, so this list was
# collected from the archive_fmt and filename_fmt of every gallery-dl
# extractor. Nested keys are written as tuples, e.g. ('post', 'id') for
# `{post[id]}`.
POST_ID_KEYS = (
    # Post IDs
    'tweet_id',                 # twitter
    'post_id',                  # instagram, bluesky, pixiv sketch, ...
    'postId',                   # 8chan, fikfap
    'postid',                   # nozomi
    ('post', 'id'),             # boosty, blogger, bellazon, livedoor, koofr
    ('status', 'id'),           # weibo
    'submission_id',            # inkbunny, artstation challenges
    'submitid',                 # weasyl
    'journalid',                # weasyl journals
    'work_id',                  # foriio, xfolio
    'pin_id',                   # sexcom
    'plurk_id',                 # plurk
    'ugc_id',                   # steamcommunity
    # Galleries, albums and chapters, where `id` usually is the ID of a
    # single file in them
    'gallery_id',               # nhentai, hitomi, imagefap, imagechest, ...
    ('gallery', 'id'),          # flickr galleries, imageshack, xvideos
    'gid',                      # exhentai, architizer
    'album_id',                 # bunkr, cyberdrop, erome, catbox, ...
    ('album', 'id'),            # imgur, flickr, artstation, luscious
    'chapter_id',               # mangadex, hentai2read, mangareader, ...
    'issue_id',                 # batcave
    'set_id',                   # bakashots
    'title_id',                 # naver-webtoon
    # The generic ID used by most extractors (tiktok, pixiv, reddit,
    # danbooru, kemono, tumblr, ...)
    'id',
    # IDs of single files, for extractors without any of the above
    'index',                    # deviantart, hentaifoundry
    'image_id',                 # dynastyscans, seiga
    'video_id',                 # xasiat
    'media_id',                 # ganknow
    'message_id',               # discord
    ('audioFile', 'id'),        # audiochan
    'dataid',                   # nozomi
    'encoded_id',               # goonbox
    'document_id',              # harvardlawnuremberg
    'listing_id',               # vanlifetrader
    'model_id',                 # thefap
    'uid',                      # naver-chzzk
    'pid',                      # wikifeet
)


def get_post_id(file_meta):
    """
    Return the ID of the post a file belongs to, or None if the gallery-dl
    metadata doesn't contain one.
    """
    for key in POST_ID_KEYS:
        value = file_meta
        for part in (key if isinstance(key, tuple) else (key,)):
            value = value.get(part) if isinstance(value, dict) else None
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            continue
        # Some extractors use 0 for "no post", e.g. Twitter avatars
        value = str(value).strip()
        if value and value != '0':
            return value
    return None


def get_itemname(file_meta, basename):
    """
    Build an archive.org identifier, `{platform}-{id}`, from the gallery-dl
    metadata of a file. All files of the same post share one identifier.
    Falls back to the basename of the downloaded file when the metadata has
    no post ID.
    """
    category = file_meta.get('category') or 'gallery-dl'
    post_id = get_post_id(file_meta) or os.path.basename(basename)
    # Remove illegal characters in identifier; archive.org identifiers are
    # limited to 100 characters
    return sanitize_identifier('%s-%s' % (category, post_id))[:100]


def check_is_file_empty(filepath):
    """
    Check whether file is empty or not.

    :param filepath:  Path of a file that will be checked.
    :return:          True if the file empty.
    """
    if os.path.exists(filepath):
        return os.stat(filepath).st_size == 0
    else:
        raise FileNotFoundError("Path '%s' doesn't exist" % filepath)
