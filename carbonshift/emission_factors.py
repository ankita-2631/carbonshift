"""Spend-based embodied-carbon resolver (Scope 3, purchased goods & services).

Turns a purchase's *spend* into an embodied-carbon estimate using published
spend-based emission factors (kg CO2e per US dollar), the standard first-pass
method in GHG-Protocol Scope 3 accounting:

    kg_co2e = spend * emission_factor(category)

The factors below are REAL published values from the US EPA *Supply Chain GHG
Emission Factors for US Industries and Commodities* dataset (v1.2, GHG data year
2019), the "Supply Chain Emission Factors with Margins" series, expressed in
kg CO2e per US dollar of purchaser-price spend (2021 USD). Source:
https://catalog.data.gov/dataset/supply-chain-greenhouse-gas-emission-factors-v1-2-by-naics-6

Each factor is tied to a specific 2017 NAICS commodity code, so every estimate
carries a citable provenance string rather than a hand-typed number. The figures
are fully offline (no API key). To raise accuracy, swap ``_FACTORS`` for a live
feed (e.g. Climatiq or the full EPA/DEFRA tables) without touching the agents —
they consume ``PurchaseLine.kg_co2e`` either way.
"""
from __future__ import annotations

# (keyword match, kg CO2e per USD, NAICS code, NAICS commodity title)
# Real EPA Supply Chain GHG Emission Factors v1.2 (with margins, 2021 USD).
_FACTORS: tuple[tuple[tuple[str, ...], float, str, str], ...] = (
    (("paper", "stationery", "envelope", "notebook"),
     0.420, "322230", "Stationery Product Manufacturing"),
    (("print", "printing", "brochure", "leaflet"),
     0.347, "323111", "Commercial Printing (except Screen and Books)"),
    (("laptop", "computer", "server", "hardware", "device", "monitor",
      "electronic", "it ", "peripheral"),
     0.110, "334111", "Electronic Computer Manufacturing"),
    (("phone", "wireless", "radio", "comms equipment"),
     0.215, "334220", "Radio, TV & Wireless Communications Equipment Manufacturing"),
    (("packaging", "plastic", "film", "wrap", "shrink"),
     0.610, "326112", "Plastics Packaging Film and Sheet Manufacturing"),
    (("box", "carton", "corrugated", "fiberboard"),
     0.490, "322211", "Corrugated and Solid Fiber Box Manufacturing"),
    (("merch", "apparel", "uniform", "garment", "clothing", "tote",
      "textile", "cotton", "shirt"),
     0.145, "315210", "Cut and Sew Apparel Contractors"),
    (("booth", "stand", "exhibition", "showcase", "partition", "shelving", "display"),
     0.340, "337215", "Showcase, Partition, Shelving, and Locker Manufacturing"),
    (("sign", "signage", "banner"),
     0.320, "339950", "Sign Manufacturing"),
    (("furniture", "fit-out", "fitout", "chair", "desk", "cabinet"),
     0.300, "337127", "Institutional Furniture Manufacturing"),
    (("reagent", "chemical", "solvent", "lab", "organic compound"),
     1.510, "325199", "All Other Basic Organic Chemical Manufacturing"),
    (("cloud", "hosting", "data centre", "data center", "compute", "storage"),
     0.150, "518210", "Data Processing, Hosting, and Related Services"),
    (("software", "saas", "licen", "subscription", "app "),
     0.097, "541511", "Custom Computer Programming Services"),
    (("freight", "logistics", "shipping", "courier", "delivery", "haulage", "trucking"),
     1.110, "484121", "General Freight Trucking, Long-Distance, Truckload"),
    (("catering", "food", "beverage", "hospitality", "canteen"),
     0.150, "722310", "Food Service Contractors"),
    (("consult", "legal", "audit", "advisory", "professional service", "lawyer"),
     0.050, "541110", "Offices of Lawyers"),
)

# Conservative default for unmatched mixed goods & services (not a specific NAICS row).
_DEFAULT_FACTOR = 0.300
_DEFAULT_CODE = "n/a"
_DEFAULT_TITLE = "unmatched mixed goods & services (conservative default)"

DATASET = "EPA Supply Chain GHG Emission Factors v1.2 (2021 USD, with margins)"


def lookup_factor(name: str) -> tuple[float, str, str]:
    """Return ``(factor, naics_code, naics_title)`` for an item name via keyword match."""
    text = name.lower()
    for keywords, factor, code, title in _FACTORS:
        if any(k in text for k in keywords):
            return factor, code, title
    return _DEFAULT_FACTOR, _DEFAULT_CODE, _DEFAULT_TITLE


def estimate_embodied_kg(name: str, cost: float) -> tuple[float, str]:
    """Estimate embodied carbon (kg CO2e) from spend using a published EPA factor.

    Returns ``(kg_co2e, source)`` where ``source`` is a citable provenance string, e.g.
    ``"EPA Supply Chain GHG Emission Factors v1.2 (2021 USD, with margins) ·
    NAICS 315210 Cut and Sew Apparel Contractors @ 0.145 kg/USD"``.
    """
    factor, code, title = lookup_factor(name)
    kg = max(0.0, float(cost)) * factor
    naics = f"NAICS {code} {title}" if code != _DEFAULT_CODE else title
    source = f"{DATASET} · {naics} @ {factor:.3f} kg/USD"
    return kg, source
