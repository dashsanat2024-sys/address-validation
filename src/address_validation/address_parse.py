"""Parse UK vendor addresses without comma separators."""

from __future__ import annotations

import re

from .schema import StandardAddress

STREET_SUFFIX = (
    r"Road|Street|Lane|Avenue|Drive|Way|Close|Crescent|Parade|Place|Court|"
    r"Gardens|Grove|Hill|Row|Square|Terrace|Yard|Walk|View|Park|Mews|Meadow|"
    r"Green|Mall|Bypass|Bridge|Arcade|Approach|Boulevard|Quay|Wharf|Vale|"
    r"Rise|End|Gate|Path|Track|Village|Villas|Works|Chase|Circus|Drove|"
    r"Grange|Link|Manor|Nook|Passage|Point|Promenade|Ridge|Spinney|"
    r"Springs|Strand|Wynd|Rd|St|Ln|Ave|Dr|Ct|Pl"
)

STREET_LINE_RE = re.compile(
    rf"\b(\d+[A-Za-z]?)\s+([A-Za-z''\-\.]+(?:\s+[A-Za-z''\-\.]+)*\s+(?:{STREET_SUFFIX}))\b",
    re.IGNORECASE,
)

FLAT_PREFIX_RE = re.compile(
    r"(?i)^(apartment|apt|flat|unit|suite|room|studio|penthouse)\s*(\d+[a-z]?)\s*(.*)$"
)

REVERSED_STREET_RE = re.compile(
    rf"(?is)^(?P<road>[A-Za-z''\-\.]+(?:\s+[A-Za-z''\-\.]+)*\s+(?:{STREET_SUFFIX}))\s+"
    r"(?P<number>\d+[A-Za-z]?)\s+"
    r"(?P<unit>(?:apartment|apt|flat|unit|suite|room)\s*\d+[A-Za-z]?)\s+"
    r"(?P<tail>[A-Za-z''\-\.\s]+)$"
)

ORG_UNIT_RE = re.compile(
    r"(?i)^(.+?)\s+(unit|flat|suite|room)\s+(\d+[a-z]?)\s+(.+)$"
)

PARK_AREA_RE = re.compile(r"(?i)\b(park|estate|industrial|trading|business\s+park)\b")

ROAD_SUFFIX_RE = re.compile(
    rf"(?i)\b({STREET_SUFFIX})\s*$"
)

def _is_business_park_segment(seg: str) -> bool:
    if PARK_AREA_RE.search(seg):
        return True
    # "Pride Park", "Business Park" — area names, not thoroughfares
    if re.search(r"(?i)(?<![A-Za-z])(?:\w+\s+)?park\s*$", seg):
        if not re.search(r"(?i)\bpark\s+(road|way|street|lane|drive|avenue)\b", seg):
            return True
    return False


def _is_road_segment(seg: str) -> bool:
    if _is_business_park_segment(seg):
        return False
    return bool(ROAD_SUFFIX_RE.search(seg))


def _smart_title(text: str) -> str:
    titled = (text or "").strip().title()
    return re.sub(r"'S\b", "'s", titled)


def parse_space_separated(text: str, customer_id: str = "") -> StandardAddress | None:
    """
    Parse single-line space-separated UK addresses, e.g.:
    'Apartment 7 Elliot's Yard 8 Gulson Road Coventry'
    """
    text = (text or "").strip()
    if not text or "," in text:
        return None

    reversed_match = REVERSED_STREET_RE.match(text)
    if reversed_match:
        addr = StandardAddress(customer_id=customer_id, country="GB", time_zone="GMTUK")
        addr.street_4 = _smart_title(reversed_match.group("road").strip())
        addr.street_house_number = reversed_match.group("number").strip()
        addr.street_2 = _smart_title(reversed_match.group("unit").strip())
        tail = reversed_match.group("tail").strip()
        if " " in tail:
            building, city = tail.rsplit(" ", 1)
            addr.street_3 = _smart_title(building.strip())
            addr.other_city = _smart_title(city.strip())
        else:
            addr.other_city = _smart_title(tail)
        return addr

    matches = list(STREET_LINE_RE.finditer(text))
    if not matches:
        return None

    match = matches[-1]
    addr = StandardAddress(customer_id=customer_id, country="GB", time_zone="GMTUK")
    addr.street_house_number = match.group(1)
    addr.street_4 = _smart_title(match.group(2).strip())

    before = text[: match.start()].strip()
    after = text[match.end() :].strip()
    if after:
        addr.other_city = _smart_title(after)

    if before:
        flat_match = FLAT_PREFIX_RE.match(before)
        if flat_match:
            addr.street_2 = f"{flat_match.group(1).title()} {flat_match.group(2)}"
            building = flat_match.group(3).strip()
            if building:
                addr.street_3 = _smart_title(building)
        else:
            addr.street_3 = _smart_title(before)

    return addr


def parse_business_comma_address(text: str, customer_id: str = "") -> StandardAddress | None:
    """
    Business / industrial comma addresses, e.g.:
    'COMEX 2000 UNIT 3 STADIUM BUSINESS COURT, MILLENNIUM WAY, PRIDE PARK, DERBY'
    """
    text = (text or "").strip()
    if not text or "," not in text:
        return None

    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) < 3:
        return None

    first = parts[0]
    org_match = ORG_UNIT_RE.match(first)
    if not org_match:
        return None

    addr = StandardAddress(customer_id=customer_id, country="GB", time_zone="GMTUK")
    addr.co = org_match.group(1).strip().upper()
    unit_label = org_match.group(2).upper()
    addr.street_2 = f"{unit_label} {org_match.group(3)}"
    addr.street_3 = _smart_title(org_match.group(4).strip())

    city = _smart_title(parts[-1])
    middle = parts[1:-1]

    roads: list[str] = []
    areas: list[str] = []
    for segment in middle:
        seg = segment.strip()
        if not seg:
            continue
        if _is_road_segment(seg):
            roads.append(_smart_title(seg))
        else:
            areas.append(_smart_title(seg))

    if areas and roads:
        addr.street_4 = areas[0]
        addr.street_5 = roads[0]
    elif areas:
        addr.street_4 = areas[0]
    elif roads:
        addr.street_4 = roads[0]

    addr.district = city.upper()
    addr.other_city = city.upper()
    return addr
