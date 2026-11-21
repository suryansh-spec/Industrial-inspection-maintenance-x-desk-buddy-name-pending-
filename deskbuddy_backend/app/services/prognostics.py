"""Equipment Age & Remaining Useful Life (RUL) Prognostics Engine.

Combines:
1. Equipment Operating Age tracking (cumulative running hours since commissioning).
2. ISO 10816-3 Vibration Severity Classification (Zone A: Good, Zone B: Acceptable, Zone C: Alert, Zone D: Critical).
3. Exponential Degradation & Remaining Useful Life (RUL) Regression:
   RMS(t) = RMS_0 * exp(lambda * t)
   Projects the exact breakdown timeline: "Will stop working in next __ days / months".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
from typing import Any, Dict, List, Optional


# ISO 10816-3 Velocity RMS thresholds for medium industrial motors (15kW - 300kW, rigid support)
ISO_ZONE_A_GOOD = 1.8         # mm/s (Healthy)
ISO_ZONE_B_ACCEPTABLE = 4.5   # mm/s (Normal operational wear)
ISO_ZONE_C_WARNING = 11.2     # mm/s (Unsatisfactory, plan maintenance)
ISO_ZONE_D_FAILURE = 18.0     # mm/s (Imminent bearing seizure / breakdown)


@dataclass
class EquipmentRecord:
    motor_id: str
    name: str = "Industrial Induction Motor"
    commission_date: datetime = field(default_factory=lambda: datetime(2026, 4, 15))
    cumulative_run_hours: float = 2480.0
    average_hours_per_day: float = 16.0
    baseline_rms_mm_s: float = 0.85
    current_rms_mm_s: float = 2.40
    latest_diagnosis: str = "Normal Baseline"
    latest_confidence: float = 0.985
    defect_size_inches: float = 0.000


class EquipmentPrognosticsEngine:
    """Calculates equipment age, wear severity, and failure timeline."""

    def __init__(self) -> None:
        # Default mock fleet records
        self._fleet: Dict[str, EquipmentRecord] = {
            "motor_1": EquipmentRecord(
                motor_id="motor_1",
                name="Main Water Pump Drive",
                commission_date=datetime(2026, 5, 1),
                cumulative_run_hours=3120.0,
                average_hours_per_day=18.0,
                baseline_rms_mm_s=0.92,
                current_rms_mm_s=3.15,
                latest_diagnosis="Normal Baseline",
                latest_confidence=0.99,
                defect_size_inches=0.000,
            ),
            "motor_2": EquipmentRecord(
                motor_id="motor_2",
                name="Air Compressor Motor",
                commission_date=datetime(2026, 2, 10),
                cumulative_run_hours=4480.0,
                average_hours_per_day=20.0,
                baseline_rms_mm_s=1.10,
                current_rms_mm_s=8.45,
                latest_diagnosis="Inner Race Fault (0.014\")",
                latest_confidence=0.965,
                defect_size_inches=0.014,
            ),
        }

    def get_or_create(self, motor_id: str) -> EquipmentRecord:
        if motor_id not in self._fleet:
            self._fleet[motor_id] = EquipmentRecord(motor_id=motor_id)
        return self._fleet[motor_id]

    def update_telemetry(
        self,
        motor_id: str,
        rms_mm_s: float,
        diagnosis: str,
        confidence: float,
        delta_run_hours: float = 0.5,
    ) -> None:
        """Update live telemetry for an equipment unit."""
        eq = self.get_or_create(motor_id)
        eq.current_rms_mm_s = max(0.1, rms_mm_s)
        eq.latest_diagnosis = diagnosis
        eq.latest_confidence = confidence
        eq.cumulative_run_hours += max(0.0, delta_run_hours)

    def calculate_rul(self, motor_id: str) -> Dict[str, Any]:
        """Compute equipment age, health percentage, and days until predicted breakdown."""
        eq = self.get_or_create(motor_id)
        now = datetime.now()

        # 1. Operational Age
        days_since_commission = max(1, (now - eq.commission_date).days)
        months_approx = round(days_since_commission / 30.4, 1)

        # 2. ISO 10816-3 Severity Assessment
        rms = eq.current_rms_mm_s
        if rms < ISO_ZONE_A_GOOD:
            iso_zone = "Zone A (Good)"
            health_pct = 95.0 + max(0.0, (ISO_ZONE_A_GOOD - rms) / ISO_ZONE_A_GOOD * 5.0)
            wear_stage = "Stage 0: Pristine / Running-in"
        elif rms < ISO_ZONE_B_ACCEPTABLE:
            iso_zone = "Zone B (Acceptable)"
            frac = (rms - ISO_ZONE_A_GOOD) / (ISO_ZONE_B_ACCEPTABLE - ISO_ZONE_A_GOOD)
            health_pct = 95.0 - (frac * 25.0)  # 70% - 95%
            wear_stage = "Stage 1: Normal Operational Wear"
        elif rms < ISO_ZONE_C_WARNING:
            iso_zone = "Zone C (Unsatisfactory / Warning)"
            frac = (rms - ISO_ZONE_B_ACCEPTABLE) / (ISO_ZONE_C_WARNING - ISO_ZONE_B_ACCEPTABLE)
            health_pct = 70.0 - (frac * 35.0)  # 35% - 70%
            wear_stage = "Stage 2: Micro-pitting & Local Fatigue"
        else:
            iso_zone = "Zone D (Critical Hazard)"
            frac = min(1.0, (rms - ISO_ZONE_C_WARNING) / (ISO_ZONE_D_FAILURE - ISO_ZONE_C_WARNING))
            health_pct = max(2.0, 35.0 - (frac * 33.0))  # 2% - 35%
            wear_stage = "Stage 3: Severe Spalling & Seizure Risk"

        health_pct = round(max(1.0, min(100.0, health_pct)), 1)

        # 3. Remaining Useful Life (RUL) Calculation
        # Degradation drift rate: lambda derived from current operating hours and baseline
        # ln(RMS / RMS_0) / T_run
        ratio = max(1.01, rms / max(0.2, eq.baseline_rms_mm_s))
        drift_rate = math.log(ratio) / max(100.0, eq.cumulative_run_hours)
        drift_rate = max(0.00005, min(0.005, drift_rate))

        # Time until failure threshold (ISO_ZONE_D_FAILURE)
        if rms >= ISO_ZONE_D_FAILURE:
            remaining_hours = 0.0
        else:
            remaining_hours = math.log(ISO_ZONE_D_FAILURE / rms) / drift_rate

        # Convert operating hours to calendar days
        daily_hours = max(1.0, eq.average_hours_per_day)
        remaining_days = int(round(remaining_hours / daily_hours))
        remaining_months = round(remaining_days / 30.4, 1)

        predicted_failure_date = now + timedelta(days=remaining_days)

        # 4. Action Recommendation
        if remaining_days <= 14:
            action = "CRITICAL: Urgent bearing overhaul. Seizure expected within 2 weeks."
            urgency = "critical"
        elif remaining_days <= 45:
            action = "HIGH: Order replacement bearings. Schedule replacement within 30 days."
            urgency = "high"
        elif remaining_days <= 90:
            action = "MODERATE: Monitor vibration twice weekly. Check lubrication levels."
            urgency = "medium"
        else:
            action = "NORMAL: Routine monthly condition monitoring."
            urgency = "low"

        return {
            "motor_id": eq.motor_id,
            "name": eq.name,
            "commission_date": eq.commission_date.strftime("%Y-%m-%d"),
            "operational_age": {
                "run_hours": round(eq.cumulative_run_hours, 1),
                "calendar_days": days_since_commission,
                "calendar_months": months_approx,
                "summary": f"{months_approx} months active ({int(eq.cumulative_run_hours):,} operating hrs)",
            },
            "vibration_metrics": {
                "current_rms_mm_s": round(rms, 2),
                "baseline_rms_mm_s": round(eq.baseline_rms_mm_s, 2),
                "iso_10816_zone": iso_zone,
                "wear_stage": wear_stage,
                "diagnosis": eq.latest_diagnosis,
                "confidence": round(eq.latest_confidence * 100, 1),
            },
            "prognostics": {
                "health_index_pct": health_pct,
                "rul_operating_hours": int(round(remaining_hours)),
                "rul_days": remaining_days,
                "rul_months": remaining_months,
                "timeline_forecast": (
                    f"Stop working in ~{remaining_days} days ({remaining_months} months)"
                    if remaining_days > 0
                    else "Breakdown imminent"
                ),
                "projected_failure_date": predicted_failure_date.strftime("%B %d, %Y"),
                "confidence_margin_days": max(2, int(round(remaining_days * 0.12))),
                "urgency": urgency,
                "action_recommendation": action,
            },
        }


prognostics_engine = EquipmentPrognosticsEngine()
