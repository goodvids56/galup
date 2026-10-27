import os
import re
import json
import hashlib
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
    # single file in them (see CONTAINER_ID_KEYS)
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


# Keys of POST_ID_KEYS shared by all files of a gallery, album or chapter
CONTAINER_ID_KEYS = POST_ID_KEYS[POST_ID_KEYS.index('gallery_id'):
                                 POST_ID_KEYS.index('id')]


def _find_post_id(file_meta):
    """
    Return a tuple of the POST_ID_KEYS key found in the gallery-dl metadata
    and its value, or (None, None).
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
            return key, value
    return None, None


def get_post_id(file_meta):
    """
    Return the ID of the post a file belongs to, or None if the gallery-dl
    metadata doesn't contain one.
    """
    return _find_post_id(file_meta)[1]


def get_filename(file_meta):
    """
    Build the name of a downloaded file, without its extension, from its
    gallery-dl metadata: `{id}`, or `{id}_{num}` when the post has several
    files. Returns None if the metadata has no post ID.
    """
    key, post_id = _find_post_id(file_meta)
    if post_id is None:
        return None

    # Position of the file in the post. Posts with a single file can still
    # have `num` set (e.g. Twitter), which `count` tells apart.
    index = file_meta.get('num') or file_meta.get('page')
    if isinstance(index, int) and not isinstance(index, bool) and index > 0 \
            and file_meta.get('count') != 1:
        return '%s_%d' % (post_id, index)

    # Without a position, tell the files of a post apart by their own ID,
    # e.g. the files of a Bunkr album
    file_id = file_meta.get('id')
    if isinstance(file_id, (str, int)) and not isinstance(file_id, bool) \
            and str(file_id).strip() and str(file_id).strip() != post_id:
        return '%s_%s' % (post_id, str(file_id).strip())

    # All files of a gallery or album share its ID, so keep their original
    # name too
    if key in CONTAINER_ID_KEYS and file_meta.get('filename'):
        return '%s_%s' % (post_id, file_meta['filename'])

    return post_id


# gallery-dl metadata keys that can hold the URL of a post's thumbnail, in
# order of preference. Nested keys are written as tuples, with list indexes
# as numbers.
THUMBNAIL_KEYS = (
    ('video', 'originCover'),   # tiktok videos
    ('video', 'cover'),
    ('imagePost', 'cover', 'imageURL', 'urlList', 0),   # tiktok slideshows
    'thumbnail',                # reddit, nhentai, ...
    'thumbnail_url',
    'thumbnailUrl',
    'thumb',
    'thumb_url',
    'cover',
    'cover_url',
    'poster',
    'poster_url',
    'preview_url',
)


def get_thumbnail_url(post_meta):
    """
    Return the URL of a post's thumbnail found in its gallery-dl metadata,
    or None.
    """
    for key in THUMBNAIL_KEYS:
        value = post_meta
        for part in (key if isinstance(key, tuple) else (key,)):
            if isinstance(part, int):
                value = value[part] if isinstance(value, list) and \
                    len(value) > part else None
            else:
                value = value.get(part) if isinstance(value, dict) else None
        if isinstance(value, str) and value.startswith(('http://',
                                                        'https://')):
            return value
    return None


def get_post_name(post_meta):
    """
    Name a post from its gallery-dl metadata: its ID, or for posts without
    one, the name of its file or a hash of the metadata.
    """
    post_id = get_post_id(post_meta)
    if post_id is not None:
        return post_id
    filename = post_meta.get('filename')
    if isinstance(filename, str) and filename:
        return filename
    meta = json.dumps(post_meta, sort_keys=True, default=str)
    return hashlib.md5(meta.encode('utf-8')).hexdigest()[:16]


# Official names of platforms by gallery-dl extractor category, for those
# whose name isn't just the capitalized category (see `get_platform_name`).
# Taken from the CATEGORY_MAP of gallery-dl's scripts/supportedsites.py,
# without spaces so they can be used in archive.org identifiers.
PLATFORM_NAMES = {
    '35photo':          '35PHOTO',
    'adultempire':      'AdultEmpire',
    'agnph':            'AGNPH',
    'ahottie':          'AHottie',
    'aibooru':          'AIBooru',
    'allporncomic':     'AllPornComic',
    'archiveofsins':    'ArchiveofSins',
    'artstation':       'ArtStation',
    'atfbooru':         'ATFBooru',
    'azurlanewiki':     'AzurLaneWiki',
    'baraag':           'baraag',
    'bbc':              'BBC',
    'blacktowhite':     'BlacktoWhite',
    'booth':            'BOOTH',
    'celebforum':       'celebforum',
    'comicvine':        'ComicVine',
    'cyberfile':        'CyberFile',
    'deviantart':       'DeviantArt',
    'drawfriends':      'DrawFriends',
    'e621':             'e621',
    'e6ai':             'e6AI',
    'e926':             'e926',
    'eporner':          'EPORNER',
    'erome':            'EroMe',
    'fanbox':           'pixivFANBOX',
    'fashionnova':      'FashionNova',
    'fikfap':           'FikFap',
    'fitnakedgirls':    'FitNakedGirls',
    'foriio':           'foriio',
    'furaffinity':      'FurAffinity',
    'girlswithmuscle':  'GirlswithMuscle',
    'hatenablog':       'HatenaBlog',
    'hbrowse':          'HBrowse',
    'hentai2read':      'Hentai2Read',
    'hentaicosplay':    'HentaiCosplay',
    'hentaienvy':       'HentaiEnvy',
    'hentaiera':        'HentaiEra',
    'hentaifoundry':    'HentaiFoundry',
    'hentaifox':        'HentaiFox',
    'hentaihand':       'HentaiHand',
    'hentaihere':       'HentaiHere',
    'hentainexus':      'HentaiNexus',
    'hentairox':        'HentaiRox',
    'hentaizap':        'HentaiZap',
    'hiperdex':         'HiperDEX',
    'horne':            'horne',
    'idolcomplex':      'IdolComplex',
    'imagebam':         'ImageBam',
    'imagechest':       'ImageChest',
    'imagefap':         'ImageFap',
    'imagepond':        'ImagePond',
    'imageshack':       'ImageShack',
    'imagetwist':       'ImageTwist',
    'imgadult':         'ImgAdult',
    'imgbb':            'ImgBB',
    'imgbox':           'imgbox',
    'imgpile':          'imgpile',
    'imgpv':            'IMGPV',
    'imgth':            'imgth',
    'imhentai':         'IMHentai',
    'joyreactor':       'JoyReactor',
    'jpgfish':          'JPGFish',
    'kaliscan':         'KaliScan',
    'leakgallery':      'LeakGallery',
    'lofter':           'LOFTER',
    'mangadex':         'MangaDex',
    'mangafire':        'MangaFire',
    'mangafox':         'MangaFox',
    'mangafreak':       'MangaFreak',
    'mangahere':        'MangaHere',
    'mangakakalot':     'MangaKakalot',
    'manganato':        'MangaNato',
    'mangapark':        'MangaPark',
    'mangaread':        'MangaRead',
    'mangareader':      'MangaReader',
    'mangataro':        'MangaTaro',
    'mangatown':        'MangaTown',
    'mediawiki':        'MediaWiki',
    'micmicidol':       'MICMICIDOL',
    'mixdrop':          'MixDrop',
    'myhentaigallery':  'MyHentaiGallery',
    'nhentai':          'nhentai',
    'nijie':            'nijie',
    'ohpolly':          'OhPolly',
    'omgmiamiswimwear': 'OmgMiamiSwimwear',
    'pholder':          'pholder',
    'photovogue':       'PhotoVogue',
    'picstate':         'PicState',
    'pidgiwiki':        'PidgiWiki',
    'pixeldrain':       'pixeldrain',
    'pixhost':          'PiXhost',
    'pixiv':            'pixiv',
    'pornimage':        'PornImage',
    'pornreactor':      'PornReactor',
    'readcomiconline':  'ReadComicOnline',
    'redgifs':          'RedGIFs',
    'rozenarcana':      'RozenArcana',
    'rule34hentai':     'Rule34Hentai',
    'rule34world':      'Rule34World',
    'rule34xyz':        'Rule34XYZ',
    'sankakucomplex':   'SankakuComplex',
    'schalenetwork':    'SchaleNetwork',
    'senmanga':         'SenManga',
    'simplyhentai':     'SimplyHentai',
    'sizebooru':        'SizeBooru',
    'slickpic':         'SlickPic',
    'slideshare':       'SlideShare',
    'smugmug':          'SmugMug',
    'speakerdeck':      'SpeakerDeck',
    'steamgriddb':      'SteamGridDB',
    'subscribestar':    'SubscribeStar',
    'tcbscans':         'TCBScans',
    'thatpervert':      'ThatPervert',
    'thefap':           'TheFap',
    'thehentaiworld':   'TheHentaiWorld',
    'tiktok':           'TikTok',
    'tmohentai':        'TMOHentai',
    'tumblrgallery':    'TumblrGallery',
    'visuabusters':     'VISUABUSTERS',
    'vk':               'VK',
    'vsco':             'VSCO',
    'wallpapercave':    'WallpaperCave',
    'webmshare':        'webmshare',
    'weebcentral':      'WeebCentral',
    'weebdex':          'WeebDex',
    'wikimediacommons': 'WikimediaCommons',
    'xbunkr':           'xBunkr',
    'xhamster':         'xHamster',
    'xvideos':          'XVideos',
    'yourlesbians':     'YourLesbians',
}


def get_platform_name(category):
    """
    Return the official name of a platform from its gallery-dl extractor
    category, e.g. `TikTok` for `tiktok` or `Twitter` for `twitter`.
    """
    if not category:
        return 'gallery-dl'
    return PLATFORM_NAMES.get(category) or category.capitalize()


def get_itemname(category, post_name):
    """
    Build an archive.org identifier, `{platform}-{id}`, from a gallery-dl
    extractor category and the name of a post (see `get_post_name`).
    """
    # Remove illegal characters in identifier; archive.org identifiers are
    # limited to 100 characters
    return sanitize_identifier('%s-%s' % (
        get_platform_name(category),
        os.path.basename(post_name),
    ))[:100]


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
