"""Google Safe Browsing (v4 Lookup API): is the store on Google's list of unsafe sites?

Terms that shape this module (see docs/DECISIONS.md, 2026-11-24):
- free, for non-commercial use only;
- results carry the attribution "Advisory provided by Google" with a link, and
  warnings use hedged wording ("suspected", "may");
- a result may not be used after its cacheDuration (about 5 minutes);
- the URL is sent to Google, which may use it (stated on the web page).
The key is sent in a header, never in the URL, so it doesn't end up in logs.
"""

import os

import httpx

from app.signals.base import Finding, SignalUnavailable, Store

LOOKUP_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
ATTRIBUTION = "Advisory provided by Google: https://developers.google.com/safe-browsing/v4/advisory"
THREAT_WORDS = {
    "MALWARE": "malware",
    "SOCIAL_ENGINEERING": "phishing or deceptive content",
    "UNWANTED_SOFTWARE": "unwanted software",
    "POTENTIALLY_HARMFUL_APPLICATION": "potentially harmful apps",
}


class SafeBrowsingSignal:
    name = "safe_browsing"
    label = "Google Safe Browsing"
    timeout_seconds = 5.0

    def __init__(self, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("GOOGLE_SAFE_BROWSING_API_KEY", "")
        self._transport = transport

    async def check(self, store: Store) -> Finding:
        if not self._api_key:
            raise SignalUnavailable("not configured on this server.")
        # Check both the exact link and the site's home page.
        urls = sorted({store.url, f"https://{store.domain}/"})
        body = {
            "client": {"clientId": "social-commerce-reliability-reporter", "clientVersion": "0.1.0"},
            "threatInfo": {
                "threatTypes": list(THREAT_WORDS),
                "platformTypes": ["ANY_PLATFORM"],
                "threatEntryTypes": ["URL"],
                "threatEntries": [{"url": u} for u in urls],
            },
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=4.0) as client:
            response = await client.post(LOOKUP_URL, json=body, headers={"x-goog-api-key": self._api_key})
            response.raise_for_status()

        threats = sorted({m["threatType"] for m in response.json().get("matches", [])})
        if threats:
            kinds = " and ".join(THREAT_WORDS.get(t, t.lower()) for t in threats)
            explanation = f"Google Safe Browsing lists this site as suspected {kinds}. It may be unsafe to visit or buy from."
        else:
            explanation = "Not on Google Safe Browsing's list of unsafe sites."
        return Finding(value={"flagged": bool(threats), "threat_types": threats}, explanation=explanation, source=ATTRIBUTION)
