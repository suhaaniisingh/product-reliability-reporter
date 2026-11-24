"""The registrable domain: the part someone actually registers and owns.

shop.glowlab.co.uk -> glowlab.co.uk, www.nike.com -> nike.com. Domain age and
popularity are looked up by this, not by the full host name. Uses the public
suffix list snapshot bundled with tldextract, so it works offline and gives the
same answer every time (no download at runtime).

Platform subdomains count as separate sites: glowlab.myshopify.com is its own
store, not part of myshopify.com. Otherwise a brand-new store would inherit
Shopify's domain age and popularity. The list's "private" section covers this.
"""

from functools import lru_cache

import tldextract

_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)


@lru_cache(maxsize=4096)
def registrable_domain(host: str) -> str:
    parts = _extract(host.lower().rstrip("."), include_psl_private_domains=True)
    return parts.top_domain_under_public_suffix or host.lower()
