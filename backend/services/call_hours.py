"""When an outbound call is allowed.

Monday through Saturday, 9:00am up to 6:00pm in the lead's local time.
Sunday is closed. 6:00pm is not a calling minute.

The zone comes from the phone's area code. Louisiana numbers (and the
other codes listed here) use that zone. America/Chicago is the business
zone, not a substitute for a Pacific or Hawaii number: 9am in New
Orleans is 7am in California and 4am in Hawaii.

An area code this map does not know uses the overlap of 9am–6pm across
Hawaii, Alaska, the Pacific, Mountain, Arizona, Central, and Eastern
zones. That window is shorter. It does not place a call before 9am or
after 6pm in any of those zones.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from services.field_norm import phone_digits

CHICAGO = ZoneInfo("America/Chicago")

# Checked together when the area code is not in the map. Arizona does not
# observe daylight saving time, so it is its own zone.
_OVERLAP_ZONES = (
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Phoenix",
    "America/Los_Angeles",
    "America/Anchorage",
    "Pacific/Honolulu",
)

_OPEN_START = 9 * 60
_OPEN_END = 18 * 60  # 6:00pm is closed


def _build(groups: dict) -> dict:
    out = {}
    for zone, codes in groups.items():
        for code in codes:
            previous = out.get(code)
            if previous and previous != zone:
                raise RuntimeError(f"area code {code} is both {previous} and {zone}")
            out[code] = zone
    return out


# Area codes assigned only when the zone is unambiguous. A split area
# code is left out on purpose so the overlap window applies.
_AREA_ZONES = _build({
    "America/Chicago": """
        205 210 214 217 218 219 224 225 228 251 254 256 262 270 274 281
        309 312 314 316 318 319 320 325 327 331 334 337 346 353 361 364
        402 405 409 414 417 430 432 447 448 464 469 479 501 502 504 507
        512 515 531 534 539 557 563 572 573 574 580 601 605 608 612 618
        620 630 636 641 651 659 660 662 682 701 708 712 713 715 726 730
        731 737 763 769 773 779 785 806 815 816 817 830 832 847 850 870
        872 901 903 913 918 920 931 936 938 940 945 952 956 972 979 985
    """.split(),
    "America/Denver": """
        303 307 385 406 505 575 719 720 801 915 970 983
    """.split(),
    "America/Phoenix": "480 520 602 623 928".split(),
    "America/Los_Angeles": """
        206 209 213 253 279 310 323 341 350 360 408 415 424 425 442 458
        503 509 510 530 541 559 562 564 619 626 628 650 657 661 669 702
        707 714 725 747 760 775 805 818 820 831 840 858 909 916 925 949
        951 971
    """.split(),
    "America/New_York": """
        201 202 203 207 212 215 216 220 223 229 231 234 239 240 248 252
        260 267 269 272 276 283 301 302 305 315 317 321 324 326 330 332
        336 339 347 351 352 363 380 386 401 404 407 410 412 413 419 423
        434 436 440 443 445 463 470 472 475 478 484 508 513 516 517 518
        540 551 561 567 570 571 582 585 586 603 606 607 609 610 614 616
        617 631 640 645 646 656 667 678 679 680 689 703 704 706 716 717
        718 724 727 732 734 740 743 754 757 762 765 770 772 774 781 786
        802 803 804 810 812 813 814 826 828 835 838 839 843 845 848 854
        856 857 859 860 862 863 864 865 878 904 906 908 910 912 914 917
        919 929 930 934 937 941 943 947 948 954 959 973 978 980 984 989
    """.split(),
    "America/Anchorage": ["907"],
    "Pacific/Honolulu": ["808"],
})


def zone_for_phone(value) -> Optional[ZoneInfo]:
    """IANA zone for a NANP number, or None when the area code is unknown."""
    digits = phone_digits(value) or ""
    if len(digits) < 3:
        return None
    name = _AREA_ZONES.get(digits[:3])
    return ZoneInfo(name) if name else None


def _open_local(local: datetime) -> bool:
    if local.weekday() == 6:
        return False
    minutes = local.hour * 60 + local.minute
    return _OPEN_START <= minutes < _OPEN_END


def within_calling_hours(when: datetime, phone) -> bool:
    """True when `when` is inside the calling window for this phone.

    `when` must be timezone-aware. An unknown area code has to be inside
    the window in every overlap zone at once.
    """
    if when.tzinfo is None:
        raise ValueError("calling-hours check needs a timezone")
    zone = zone_for_phone(phone)
    if zone is not None:
        return _open_local(when.astimezone(zone))
    return all(_open_local(when.astimezone(ZoneInfo(name))) for name in _OVERLAP_ZONES)


def hours_message(phone) -> str:
    if zone_for_phone(phone) is None:
        return (
            "Outside calling hours. This number's time zone is not on the "
            "list, so a call has to fall inside Monday–Saturday 9am–6pm in "
            "every US time zone from Hawaii to Eastern. No call was placed."
        )
    return (
        "Outside calling hours (Monday–Saturday, 9am–6pm in the lead's "
        "local time). No call was placed."
    )
