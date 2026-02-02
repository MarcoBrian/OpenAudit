from __future__ import annotations

import urllib.parse
from typing import Dict, List


def build_search_links(issue_title: str) -> List[Dict[str, str]]:
    query = urllib.parse.quote_plus(issue_title)
    return [
        {
            "source": "Solodit",
            "url": f"https://solodit.xyz/?search={query}",
            "note": "Search for similar historical cases.",
        }
    ]

