"""parse_video_url: platform, video ID and handle read from the link alone."""

import pytest

from app.extraction.video_url import parse_video_url
from app.schemas import Platform


@pytest.mark.parametrize(
    ("url", "platform", "video_id", "handle"),
    [
        ("https://www.tiktok.com/@scout2015/video/6718335390845095173", Platform.TIKTOK, "6718335390845095173", "scout2015"),
        ("https://www.tiktok.com/@glow.lab_/video/7301234567890123456?is_from_webapp=1&lang=en", Platform.TIKTOK, "7301234567890123456", "glow.lab_"),
        ("https://m.tiktok.com/@anna/photo/7300000000000000001", Platform.TIKTOK, "7300000000000000001", "anna"),
        ("https://vm.tiktok.com/ZMabc123/", Platform.TIKTOK, None, None),  # short link: needs a redirect we don't follow
        ("https://www.tiktok.com/t/ZTabc123/", Platform.TIKTOK, None, None),
        ("https://www.instagram.com/p/fA9uwTtkSN/", Platform.INSTAGRAM, "fA9uwTtkSN", None),
        ("https://www.instagram.com/reel/C1a2B3c4D5e/?igsh=abc", Platform.INSTAGRAM, "C1a2B3c4D5e", None),
        ("https://instagram.com/reels/C1a2B3c4D5e/", Platform.INSTAGRAM, "C1a2B3c4D5e", None),
        ("https://www.instagram.com/glowlab/p/C1a2B3c4D5e/", Platform.INSTAGRAM, "C1a2B3c4D5e", "glowlab"),
        ("https://www.instagram.com/glowlab/", Platform.INSTAGRAM, None, None),  # a profile, not a post
        ("https://www.youtube.com/shorts/abc123", Platform.UNKNOWN, None, None),
        ("https://tiktok.com.evil.example/@anna/video/1", Platform.UNKNOWN, None, None),  # lookalike host
    ],
)
def test_parse_video_url(url: str, platform: Platform, video_id: str | None, handle: str | None) -> None:
    info = parse_video_url(url)

    assert (info.platform, info.video_id, info.creator_handle) == (platform, video_id, handle)
