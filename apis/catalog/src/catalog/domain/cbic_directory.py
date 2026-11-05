"""Legacy curated HSN/SAC lookup, not a current statutory tax schedule.

Historic rate suggestions are not returned by the API or used for provisioning.
Use the company's dated tax masters and their reviewed official evidence for rates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class HsnSacEntry:
    code: str
    code_system: Literal["HSN", "SAC"]
    description: str
    chapter: str
    item_kind: Literal["GOODS", "SERVICE"]
    gst_rate_default: float


# Curated baseline dataset of official CBIC tariff entries across high-frequency sectors.
CBIC_DIRECTORY: tuple[HsnSacEntry, ...] = (
    # Chapter 85: Electronics, Telecommunications, Sound/Video
    HsnSacEntry(
        "8517",
        "HSN",
        "Telephone sets, smartphones and other apparatus for voice/images",
        "85",
        "GOODS",
        18.0,
    ),
    HsnSacEntry(
        "85171200",
        "HSN",
        "Smartphones and mobile phones for cellular networks",
        "85",
        "GOODS",
        18.0,
    ),
    HsnSacEntry(
        "85176290",
        "HSN",
        "Routers, modems and wireless networking equipment",
        "85",
        "GOODS",
        18.0,
    ),
    HsnSacEntry(
        "8504",
        "HSN",
        "Electrical transformers, static converters and power supplies",
        "85",
        "GOODS",
        18.0,
    ),
    HsnSacEntry(
        "8528",
        "HSN",
        "Monitors, projectors and television reception apparatus",
        "85",
        "GOODS",
        18.0,
    ),
    HsnSacEntry(
        "8544",
        "HSN",
        "Insulated wire, cable and optical fiber cables",
        "85",
        "GOODS",
        18.0,
    ),
    # Chapter 84: Machinery, Nuclear reactors, Boilers, Computers
    HsnSacEntry(
        "8471",
        "HSN",
        "Automatic data processing machines (computers, laptops, servers)",
        "84",
        "GOODS",
        18.0,
    ),
    HsnSacEntry(
        "84713010",
        "HSN",
        "Personal computers, laptops, tablets and notebooks",
        "84",
        "GOODS",
        18.0,
    ),
    HsnSacEntry(
        "8443",
        "HSN",
        "Printing machinery, computer printers, copiers and facsimiles",
        "84",
        "GOODS",
        18.0,
    ),
    HsnSacEntry(
        "8415",
        "HSN",
        "Air conditioning machines comprising motor-driven fan",
        "84",
        "GOODS",
        28.0,
    ),
    HsnSacEntry(
        "8418",
        "HSN",
        "Refrigerators, freezers and other refrigerating equipment",
        "84",
        "GOODS",
        18.0,
    ),
    # Chapter 30: Pharmaceutical products
    HsnSacEntry(
        "3004",
        "HSN",
        "Medicaments consisting of mixed or unmixed products for therapeutic use",
        "30",
        "GOODS",
        12.0,
    ),
    HsnSacEntry(
        "30049099",
        "HSN",
        "Other allopathic medicaments / pharmaceutical formulations",
        "30",
        "GOODS",
        12.0,
    ),
    HsnSacEntry(
        "3002",
        "HSN",
        "Human blood, animal blood, vaccines, toxins and cultures",
        "30",
        "GOODS",
        5.0,
    ),
    HsnSacEntry(
        "3005",
        "HSN",
        "Wadding, gauze, bandages and surgical dressings",
        "30",
        "GOODS",
        12.0,
    ),
    # Chapter 61 & 62: Apparel & Clothing
    HsnSacEntry(
        "6109",
        "HSN",
        "T-shirts, singlets and other vests, knitted or crocheted",
        "61",
        "GOODS",
        12.0,
    ),
    HsnSacEntry(
        "6203",
        "HSN",
        "Men's or boys' suits, jackets, blazers, trousers and shorts",
        "62",
        "GOODS",
        12.0,
    ),
    HsnSacEntry(
        "6204",
        "HSN",
        "Women's or girls' suits, dresses, skirts and trousers",
        "62",
        "GOODS",
        12.0,
    ),
    # Chapter 39: Plastics and articles thereof
    HsnSacEntry(
        "3923",
        "HSN",
        "Articles for the conveyance or packing of goods, of plastics",
        "39",
        "GOODS",
        18.0,
    ),
    HsnSacEntry(
        "3926",
        "HSN",
        "Other articles of plastics and articles of other materials",
        "39",
        "GOODS",
        18.0,
    ),
    # Chapter 87: Vehicles other than railway or tramway
    HsnSacEntry(
        "8703",
        "HSN",
        "Motor cars and other motor vehicles principally designed for transport",
        "87",
        "GOODS",
        28.0,
    ),
    HsnSacEntry(
        "8708",
        "HSN",
        "Parts and accessories of motor vehicles",
        "87",
        "GOODS",
        28.0,
    ),
    HsnSacEntry(
        "8711",
        "HSN",
        "Motorcycles (including mopeds) and cycles fitted with auxiliary motor",
        "87",
        "GOODS",
        28.0,
    ),
    # Chapter 10 & 04: Agro & Dairy Food Products
    HsnSacEntry(
        "0401",
        "HSN",
        "Milk and cream, not concentrated nor containing added sugar",
        "04",
        "GOODS",
        0.0,
    ),
    HsnSacEntry(
        "0402",
        "HSN",
        "Milk and cream, concentrated or containing added sugar",
        "04",
        "GOODS",
        5.0,
    ),
    HsnSacEntry(
        "1006",
        "HSN",
        "Rice (semi-milled, wholly milled or polished)",
        "10",
        "GOODS",
        5.0,
    ),
    # Chapter 99: Services Accounting Code (SAC)
    HsnSacEntry(
        "998311",
        "SAC",
        "Management consulting and management services",
        "99",
        "SERVICE",
        18.0,
    ),
    HsnSacEntry(
        "998313",
        "SAC",
        "Information technology (IT) consulting and support services",
        "99",
        "SERVICE",
        18.0,
    ),
    HsnSacEntry(
        "998314",
        "SAC",
        "Information technology (IT) design and development services",
        "99",
        "SERVICE",
        18.0,
    ),
    HsnSacEntry(
        "998315",
        "SAC",
        "Hosting and information technology (IT) infrastructure services",
        "99",
        "SERVICE",
        18.0,
    ),
    HsnSacEntry(
        "995411",
        "SAC",
        "Construction services of residential buildings",
        "99",
        "SERVICE",
        12.0,
    ),
    HsnSacEntry(
        "995412",
        "SAC",
        "Construction services of non-residential buildings",
        "99",
        "SERVICE",
        18.0,
    ),
    HsnSacEntry(
        "997111",
        "SAC",
        "Financial and related banking services",
        "99",
        "SERVICE",
        18.0,
    ),
    HsnSacEntry(
        "997131",
        "SAC",
        "Life insurance services",
        "99",
        "SERVICE",
        18.0,
    ),
    HsnSacEntry(
        "997132",
        "SAC",
        "Non-life insurance services",
        "99",
        "SERVICE",
        18.0,
    ),
    HsnSacEntry(
        "996511",
        "SAC",
        "Freight transport services by road",
        "99",
        "SERVICE",
        5.0,
    ),
    HsnSacEntry(
        "996512",
        "SAC",
        "Freight transport services by railway",
        "99",
        "SERVICE",
        5.0,
    ),
    HsnSacEntry(
        "996331",
        "SAC",
        "Restaurant and food service with air-conditioning",
        "99",
        "SERVICE",
        5.0,
    ),
    HsnSacEntry(
        "996311",
        "SAC",
        "Hotel accommodation services below declared tariff",
        "99",
        "SERVICE",
        12.0,
    ),
    HsnSacEntry(
        "998211",
        "SAC",
        "Legal advisory and representation services",
        "99",
        "SERVICE",
        18.0,
    ),
    HsnSacEntry(
        "998222",
        "SAC",
        "Accounting, auditing and bookkeeping services",
        "99",
        "SERVICE",
        18.0,
    ),
    HsnSacEntry(
        "998711",
        "SAC",
        "Maintenance and repair services of motor vehicles",
        "99",
        "SERVICE",
        18.0,
    ),
    HsnSacEntry(
        "998713",
        "SAC",
        "Maintenance and repair services of computers and office equipment",
        "99",
        "SERVICE",
        18.0,
    ),
)

_BY_CODE: dict[str, HsnSacEntry] = {entry.code: entry for entry in CBIC_DIRECTORY}


def lookup_hsn_sac(code: str) -> HsnSacEntry | None:
    """Look up an exact HSN or SAC code in the CBIC directory."""
    return _BY_CODE.get(code)


def search_hsn_sac(
    *,
    query: str | None = None,
    code_system: Literal["HSN", "SAC"] | None = None,
    chapter: str | None = None,
    limit: int = 50,
) -> list[HsnSacEntry]:
    """Search CBIC statutory directory with multi-field filtering."""
    results: list[HsnSacEntry] = []
    q_norm = query.strip().lower() if query else None

    for entry in CBIC_DIRECTORY:
        if code_system and entry.code_system != code_system:
            continue
        if chapter and entry.chapter != chapter:
            continue
        if q_norm:
            if (
                q_norm not in entry.code.lower()
                and q_norm not in entry.description.lower()
            ):
                continue
        results.append(entry)
        if len(results) >= limit:
            break

    return results
