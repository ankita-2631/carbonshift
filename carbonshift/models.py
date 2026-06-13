"""Data models for CarbonShift."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


@dataclass
class Job:
    """A flexible workload that can be shifted in time to run on cleaner power.

    Attributes:
        name: Human-readable job identifier.
        power_kw: Average power draw while running, in kilowatts.
        duration_hours: How long the job runs once started.
        deadline: Latest time by which the job must be finished.
        earliest_start: Earliest time the job may start (defaults to now at planning time).
        region: Grid region code the job runs in (e.g. a UK DNO region or "national").
        flexible: If False, the job is pinned to run immediately and is never shifted.
    """

    name: str
    power_kw: float
    duration_hours: float
    deadline: datetime
    earliest_start: datetime | None = None
    region: str = "national"
    flexible: bool = True


class RiskLevel(str, Enum):
    """Traffic-light rating for a scheduling decision."""

    GREEN = "green"   # clean window found, big savings
    AMBER = "amber"   # some savings, or constrained by deadline
    RED = "red"       # cannot shift / must run during dirty window


@dataclass
class ScheduleDecision:
    """The agent's decision for a single job."""

    job: Job
    chosen_start: datetime
    baseline_start: datetime
    chosen_intensity: float          # gCO2/kWh at chosen window (avg)
    baseline_intensity: float        # gCO2/kWh if run now (avg)
    kg_co2_chosen: float
    kg_co2_baseline: float
    risk: RiskLevel
    rationale: str = ""
    citations: list[str] = field(default_factory=list)
    # Money: cost of the energy at the chosen vs. baseline window (same currency unit).
    cost_chosen: float = 0.0
    cost_baseline: float = 0.0

    @property
    def kg_co2_saved(self) -> float:
        return max(0.0, self.kg_co2_baseline - self.kg_co2_chosen)

    @property
    def pct_saved(self) -> float:
        if self.kg_co2_baseline <= 0:
            return 0.0
        return 100.0 * self.kg_co2_saved / self.kg_co2_baseline

    @property
    def money_saved(self) -> float:
        return max(0.0, self.cost_baseline - self.cost_chosen)


@dataclass
class SchedulePlan:
    """The full plan across all jobs."""

    decisions: list[ScheduleDecision] = field(default_factory=list)

    @property
    def total_saved_kg(self) -> float:
        return sum(d.kg_co2_saved for d in self.decisions)

    @property
    def total_baseline_kg(self) -> float:
        return sum(d.kg_co2_baseline for d in self.decisions)

    @property
    def total_pct_saved(self) -> float:
        if self.total_baseline_kg <= 0:
            return 0.0
        return 100.0 * self.total_saved_kg / self.total_baseline_kg

    @property
    def total_money_saved(self) -> float:
        return sum(d.money_saved for d in self.decisions)


# --------------------------------------------------------------------------- #
# Travel domain                                                               #
# --------------------------------------------------------------------------- #


class TravelMode(str, Enum):
    """A way to make a trip, ordered roughly dirtiest -> cleanest."""

    CAR_PETROL = "car_petrol"
    CAR_EV = "car_ev"
    RAIL = "rail"
    VIRTUAL = "virtual"   # replace the trip with a video meeting


@dataclass
class Trip:
    """A planned business trip the TravelAgent can reason about.

    Attributes:
        name: Human-readable trip identifier.
        distance_km: One-way distance in kilometres.
        mode: The currently planned mode of travel.
        passengers: People sharing the trip (splits per-person impact for car/rail).
        round_trip: If True, distance is doubled.
        essential: If True, the trip cannot be replaced by a virtual meeting.
        relationship_critical: If True, company travel policy prefers in-person contact
            (e.g. first client meeting, team off-site); the trip may switch to a cleaner
            physical mode but should not be silently downgraded to a virtual call.
    """

    name: str
    distance_km: float
    mode: TravelMode = TravelMode.CAR_PETROL
    passengers: int = 1
    round_trip: bool = True
    essential: bool = False
    relationship_critical: bool = False


@dataclass
class TravelDecision:
    """The TravelAgent's recommendation for a single trip."""

    trip: Trip
    chosen_mode: TravelMode
    baseline_mode: TravelMode
    kg_co2_chosen: float
    kg_co2_baseline: float
    cost_chosen: float
    cost_baseline: float
    risk: RiskLevel
    rationale: str = ""
    citations: list[str] = field(default_factory=list)
    ai_classified: bool = False        # True if the agent reasoned about in-person need
    classification_note: str = ""      # one-line "why" for the in-person decision

    @property
    def kg_co2_saved(self) -> float:
        return max(0.0, self.kg_co2_baseline - self.kg_co2_chosen)

    @property
    def pct_saved(self) -> float:
        if self.kg_co2_baseline <= 0:
            return 0.0
        return 100.0 * self.kg_co2_saved / self.kg_co2_baseline

    @property
    def money_saved(self) -> float:
        return max(0.0, self.cost_baseline - self.cost_chosen)


@dataclass
class TravelPlan:
    """The full plan across all trips."""

    decisions: list[TravelDecision] = field(default_factory=list)

    @property
    def total_saved_kg(self) -> float:
        return sum(d.kg_co2_saved for d in self.decisions)

    @property
    def total_baseline_kg(self) -> float:
        return sum(d.kg_co2_baseline for d in self.decisions)

    @property
    def total_pct_saved(self) -> float:
        if self.total_baseline_kg <= 0:
            return 0.0
        return 100.0 * self.total_saved_kg / self.total_baseline_kg

    @property
    def total_money_saved(self) -> float:
        return sum(d.money_saved for d in self.decisions)


# --------------------------------------------------------------------------- #
# Generic reduction measures (Fleet, Procurement)                             #
# --------------------------------------------------------------------------- #


@dataclass
class MeasureDecision:
    """A single recommended reduction measure in any non-scheduling domain."""

    name: str
    domain: str            # "fleet" | "procurement"
    action: str            # what to do, e.g. "Switch van to EV"
    kg_co2_baseline: float
    kg_co2_chosen: float
    cost_baseline: float
    cost_chosen: float
    risk: RiskLevel
    rationale: str = ""
    citations: list[str] = field(default_factory=list)
    ai_proposed: bool = False   # True if an LLM proposed this option for a new/unknown item
    detail: str = ""            # optional extra context line (e.g. route + charging notes)

    @property
    def kg_co2_saved(self) -> float:
        return max(0.0, self.kg_co2_baseline - self.kg_co2_chosen)

    @property
    def pct_saved(self) -> float:
        if self.kg_co2_baseline <= 0:
            return 0.0
        return 100.0 * self.kg_co2_saved / self.kg_co2_baseline

    @property
    def money_saved(self) -> float:
        return max(0.0, self.cost_baseline - self.cost_chosen)


@dataclass
class MeasurePlan:
    """A set of measures within one domain."""

    domain: str = ""
    decisions: list[MeasureDecision] = field(default_factory=list)

    @property
    def total_saved_kg(self) -> float:
        return sum(d.kg_co2_saved for d in self.decisions)

    @property
    def total_baseline_kg(self) -> float:
        return sum(d.kg_co2_baseline for d in self.decisions)

    @property
    def total_pct_saved(self) -> float:
        if self.total_baseline_kg <= 0:
            return 0.0
        return 100.0 * self.total_saved_kg / self.total_baseline_kg

    @property
    def total_money_saved(self) -> float:
        return sum(d.money_saved for d in self.decisions)


# --------------------------------------------------------------------------- #
# Fleet domain (Scope 1 + 3): owned vehicles, logistics, commuting            #
# --------------------------------------------------------------------------- #


class FuelType(str, Enum):
    DIESEL = "diesel"
    PETROL = "petrol"
    EV = "ev"


@dataclass
class Vehicle:
    """A fleet/commute vehicle the FleetAgent can reason about.

    Attributes:
        name: Human-readable vehicle or route name.
        daily_km: Distance driven per day, in kilometres (the route the EV must cover
            between depot charges).
        fuel: Current fuel type.
        swappable_to_ev: If True, an EV model exists for this vehicle class. If False
            (e.g. heavy haulage), the vehicle cannot be electrified regardless of route.
        days_per_week: Operating days per week (defaults to 5).
        ev_range_km: Usable range of the candidate EV on a full charge (nameplate).
        chargers_on_route: Fallback count of rapid/public chargers along this route,
            used only when live map data is unavailable.
        depot_charging: If True, the vehicle returns to a depot/home charger overnight.
        route_lat: Latitude of the route's operating-area centre. When set (with
            ``route_lon``), the FleetAgent queries live charging-station data (Open
            Charge Map) for the real number of chargers along the route.
        route_lon: Longitude of the route's operating-area centre.
    """

    name: str
    daily_km: float
    fuel: FuelType = FuelType.DIESEL
    swappable_to_ev: bool = True
    days_per_week: int = 5
    ev_range_km: float = 250.0
    chargers_on_route: int = 0
    depot_charging: bool = True
    route_lat: float | None = None
    route_lon: float | None = None


# --------------------------------------------------------------------------- #
# Procurement domain (Scope 3): purchased goods & services                    #
# --------------------------------------------------------------------------- #


@dataclass
class PurchaseLine:
    """A purchased good/service with a lower-carbon alternative.

    Attributes:
        name: Item or category name.
        kg_co2e: Embodied carbon of the current choice (kg CO2e).
        cost: Current spend on the item (currency units).
        alt_reduction_pct: Fraction (0..1) of carbon the alternative avoids. Leave as
            None for a *new/unknown* item: the ProcurementAgent will then reason about
            the best lower-carbon alternative itself (LLM grounded in Foundry IQ).
        alt_cost_delta_pct: Cost change of the alternative (-0.1 = 10% cheaper).
        alternative: Description of the greener option.
        locked: If True, the item cannot be switched (single-source/contractual).
    """

    name: str
    kg_co2e: float
    cost: float
    alt_reduction_pct: float | None = None
    alt_cost_delta_pct: float = 0.0
    alternative: str = "Lower-carbon alternative"
    locked: bool = False
