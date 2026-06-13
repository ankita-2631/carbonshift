"""ForecastAgent — fetches and validates the grid carbon-intensity forecast."""
from __future__ import annotations

from datetime import timedelta

from ..carbon_data import CarbonForecast, get_forecast
from .base import Agent, AgentMessage, Blackboard

# A simulated grid spike lifts the near-term forecast for this many hours.
SPIKE_WINDOW_HOURS = 4


class ForecastAgent(Agent):
    """Pulls the grid forecast and rates how trustworthy it is."""

    name = "ForecastAgent"

    def process(self, bb: Blackboard) -> list[AgentMessage]:
        forecast = get_forecast(now=bb.now)
        if bb.grid_spike > 0:
            forecast = self._apply_spike(forecast, bb)
        bb.forecast = forecast

        intensities = [gco2 for (_s, _e, gco2) in forecast.points]
        lo, hi = (min(intensities), max(intensities)) if intensities else (0.0, 0.0)
        spread = hi - lo

        # Confidence: live API data is trusted; a wider clean/dirty spread means
        # more opportunity and a clearer signal to act on.
        is_live = "synthetic" not in forecast.source
        confidence = 0.9 if is_live else 0.5
        if spread < 40:  # a flat curve offers little to optimise
            confidence -= 0.2
        bb.forecast_confidence = round(max(0.0, min(1.0, confidence)), 2)

        source_kind = "live grid API" if is_live else "synthetic fallback"
        summary = (
            f"48h forecast from {source_kind}: intensity {lo:.0f}-{hi:.0f} gCO2/kWh "
            f"(spread {spread:.0f}), confidence {bb.forecast_confidence:.0%}."
        )
        msg = AgentMessage(
            sender=self.name,
            recipient="OptimizerAgent",
            intent="forecast.ready",
            summary=summary,
            payload={
                "source": forecast.source,
                "min": lo,
                "max": hi,
                "confidence": bb.forecast_confidence,
            },
        )
        bb.post(msg)
        return [msg]

    def _apply_spike(self, forecast: CarbonForecast, bb: Blackboard) -> CarbonForecast:
        """Return a copy of the forecast with the next few hours raised by the spike.

        Simulates a real grid-stress event (e.g. low wind + peak demand) so the
        optimiser visibly re-plans around dirtier near-term power. Clearly labelled
        as simulated so it is never mistaken for live data.
        """
        cutoff = bb.now + timedelta(hours=SPIKE_WINDOW_HOURS)
        bumped = [
            (s, e, g + bb.grid_spike if s < cutoff else g)
            for (s, e, g) in forecast.points
        ]
        return CarbonForecast(bumped, source=f"{forecast.source} +simulated-spike")

