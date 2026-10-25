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
# order of preference. Extractors name it differently (e.g. Twitter uses
# `tweet_id`, TikTok and Pixiv use `id`).
POST_ID_KEYS = ('tweet_id', 'post_id', 'id')


def get_post_id(file_meta):
    """
    Return the ID of the post a file belongs to, or None if the gallery-dl
    metadata doesn't contain one.
    """
    for key in POST_ID_KEYS:
        value = file_meta.get(key)
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
