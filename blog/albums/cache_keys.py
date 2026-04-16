ALBUM_LIST_CACHE_KEY = "album_list"
ALBUM_LIST_TTL = 300

ALBUM_DETAIL_TTL = 300


def get_album_detail_cache_key(album_pk):
    return f"album_detail_{album_pk}"
