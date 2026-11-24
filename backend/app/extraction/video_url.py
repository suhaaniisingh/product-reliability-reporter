"""Read what we can from a TikTok/Instagram link itself. No network call.

The platforms' oEmbed endpoints no longer return captions or creators (checked
2026-11-23), but the link's path still carries the video ID and, for TikTok, the
creator's handle: tiktok.com/@handle/video/123.
"""

import re
from urllib.parse import urlsplit

from app.schemas import Platform, VideoInfo

_TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}
# Share links like vm.tiktok.com/ZMabc123/ only redirect to the real URL. Following
# the redirect would need a network call, so we only record the platform.
_TIKTOK_SHORT_HOSTS = {"vm.tiktok.com", "vt.tiktok.com"}
_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}

_HANDLE = r"[A-Za-z0-9._]{1,30}"
_TIKTOK_POST = re.compile(rf"^/@(?P<handle>{_HANDLE})/(?:video|photo)/(?P<id>\d+)")
# /p/ = photo or carousel post, /reel/ or /reels/ = Reel, /tv/ = old IGTV links.
# Some share links put the username first: /username/p/<shortcode>/.
_INSTAGRAM_POST = re.compile(rf"^/(?:(?P<handle>{_HANDLE})/)?(?:p|reels?|tv)/(?P<id>[A-Za-z0-9_-]+)")


def parse_video_url(url: str) -> VideoInfo:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()

    if host in _TIKTOK_HOSTS:
        if match := _TIKTOK_POST.match(parts.path):
            return VideoInfo(platform=Platform.TIKTOK, video_id=match["id"], creator_handle=match["handle"])
        return VideoInfo(platform=Platform.TIKTOK, video_id=None, creator_handle=None)  # e.g. tiktok.com/t/abc

    if host in _TIKTOK_SHORT_HOSTS:
        return VideoInfo(platform=Platform.TIKTOK, video_id=None, creator_handle=None)

    if host in _INSTAGRAM_HOSTS:
        if match := _INSTAGRAM_POST.match(parts.path):
            return VideoInfo(platform=Platform.INSTAGRAM, video_id=match["id"], creator_handle=match["handle"])
        return VideoInfo(platform=Platform.INSTAGRAM, video_id=None, creator_handle=None)

    return VideoInfo(platform=Platform.UNKNOWN, video_id=None, creator_handle=None)
