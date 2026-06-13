# Grid Carbon Intensity — Reference Facts

Source: UK National Grid ESO Carbon Intensity API (https://carbonintensity.org.uk).
These facts ground CarbonShift's explanations. Cite this document as
"National Grid ESO Carbon Intensity".

## What carbon intensity means
- Carbon intensity is the grams of CO2 emitted per kilowatt-hour of electricity
  consumed (gCO2/kWh). It rises when fossil generation (gas, coal) meets demand and
  falls when wind, solar, nuclear and hydro dominate.
- Typical UK national values range from roughly 50 gCO2/kWh (very clean, windy night)
  to 350+ gCO2/kWh (dirty evening peak on a still day).

## Why intensity varies through the day
- Demand peaks in the early evening (~17:00–19:00), often met by gas, pushing
  intensity up.
- Overnight (~01:00–05:00) demand is low and wind share is often higher, lowering
  intensity.
- Midday can dip when solar output is high.
- Because of this, shifting a flexible load by a few hours commonly cuts its emissions
  by 20–60% with no change in the energy used.

## How CarbonShift computes savings
- Energy used (kWh) = power_kw x duration_hours. This is unchanged by shifting.
- Emissions (kg CO2) = energy_kWh x intensity_gPerkWh / 1000.
- Saving = emissions at "run now" window minus emissions at the chosen cleaner window.
- Only the timing changes; the work done and energy consumed stay the same.

## Constraints CarbonShift always respects
- A job is never started before its earliest_start.
- A job always finishes by its deadline.
- Jobs marked inflexible (e.g. always-on customer APIs) are never shifted.

## Honesty and limits
- Forecasts come from a third party and can be wrong; actual intensity may differ.
- CarbonShift is decision support, not a guarantee of realised savings.
