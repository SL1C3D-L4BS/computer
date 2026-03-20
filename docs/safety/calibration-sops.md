# Calibration Standard Operating Procedures

Defines calibration procedures for sensors and actuators. Uncalibrated sensors produce unreliable telemetry; unreliable telemetry causes incorrect policy decisions.

## Calibration records

All calibrations are logged in digital-twin under the asset record:
```json
{
  "asset_id": "sensor_ph_zone_a_001",
  "calibration_history": [
    {
      "date": "2026-01-15",
      "operator": "user_001",
      "method": "two_point",
      "reference_values": [4.0, 7.0],
      "measured_before": [3.85, 6.92],
      "measured_after": [4.00, 7.00],
      "coefficients": {"slope": 1.023, "offset": -0.012},
      "next_calibration_due": "2026-04-15"
    }
  ]
}
```

## SOP-001: pH probe calibration (two-point)

**Frequency**: Every 90 days; or when drift > 0.2 pH units detected  
**Materials**: pH 4.0 buffer, pH 7.0 buffer, DI water, clean containers  
**Duration**: 15 minutes

1. Remove probe from solution; rinse with DI water.
2. Insert probe in pH 4.0 buffer; wait 60 seconds for stabilization.
3. Record displayed pH; should be 4.0 ± 0.1. If not, apply correction in control software.
4. Rinse probe with DI water.
5. Insert probe in pH 7.0 buffer; wait 60 seconds.
6. Record displayed pH; should be 7.0 ± 0.1. If not, apply correction.
7. Rinse probe; return to solution.
8. Record calibration in digital-twin via ops-web: `Maintenance > Calibration > pH Probe`.
9. Set next calibration reminder (90 days).

**Pass criteria**: Probe reads within 0.05 pH units of reference at both points after calibration.  
**Fail action**: Replace probe if calibration cannot bring within spec.

## SOP-002: EC (electrical conductivity) probe calibration

**Frequency**: Every 90 days  
**Materials**: EC calibration solution (1.413 mS/cm standard), DI water  
**Duration**: 10 minutes

1. Rinse probe with DI water.
2. Submerge in 1.413 mS/cm calibration solution; wait 60 seconds.
3. Record displayed EC; verify within 1.35–1.47 mS/cm.
4. Apply correction coefficient in hydro-control service configuration.
5. Record calibration in digital-twin.
6. Set reminder 90 days out.

**Pass criteria**: EC reads 1.413 ± 0.05 mS/cm after calibration.

## SOP-003: Temperature sensor verification

**Frequency**: Every 180 days  
**Materials**: NIST-traceable thermometer, ice bath (0°C), boiling water (adjust for altitude)  
**Duration**: 20 minutes

1. Prepare ice bath: equal parts crushed ice and water. Verify 0°C on reference thermometer.
2. Insert sensor; wait 120 seconds; record reading. Should be 0 ± 0.5°C.
3. Record any offset in digital-twin configuration.
4. Repeat at known room temperature with reference thermometer.

**Pass criteria**: Reading within 0.5°C of reference at two points.

## SOP-004: Flow meter calibration

**Frequency**: Every 180 days or after maintenance  
**Materials**: Graduated container (5L minimum), stopwatch  
**Duration**: 20 minutes

1. Run water through flow meter at typical operating pressure for 60 seconds.
2. Collect water in graduated container; measure actual volume.
3. Compare to flow meter reading; calculate k-factor correction.
4. Apply correction in greenhouse-control or hydro-control service.
5. Repeat twice; verify consistency.
6. Record calibration.

**Pass criteria**: Flow reading within 5% of measured volume.

## SOP-005: Peristaltic pump dose calibration

**Frequency**: Every 30 days; after tube replacement  
**Materials**: Graduated syringe (50mL), scale accurate to 0.1g  
**Duration**: 15 minutes

1. Remove pump tubing outlet; direct into graduated syringe.
2. Run pump for exactly 10 seconds at standard speed.
3. Weigh dispensed fluid; divide by density to get volume.
4. Calculate mL/second; compare to configured dose rate.
5. Update calibration constant in hydro-control service.
6. Repeat three times; verify consistency < 2% variance.
7. Record calibration.

**Pass criteria**: Dose variance < 2% over three consecutive measurements.

## SOP-006: Rover wheel odometry calibration

**Frequency**: After drivetrain maintenance; every 6 months  
**Materials**: Measuring tape, flat surface 10m minimum  
**Duration**: 20 minutes

1. Mark start position; drive rover exactly 10m forward (teleop, straight line).
2. Measure actual distance with tape; record ROS2 `/odom` reported distance.
3. Calculate correction factor; update wheel circumference parameter in Nav2 config.
4. Repeat for rotation: rotate exactly 360° in place; verify `/odom` reports 360°.
5. Apply correction; rebuild Nav2 config; record calibration.

**Pass criteria**: Distance error < 2% over 10m; rotation error < 5° over 360°.

## SOP-007: RTK GNSS base/rover calibration

**Frequency**: After any base station move; after firmware update  
**Materials**: Surveyed reference point (or CORS reference)  
**Duration**: 60 minutes

1. Place rover antenna over known reference point.
2. Allow RTK fix to converge (minimum 15 minutes; green fix indicator).
3. Record averaged position (1000 epoch average).
4. Compare to known reference; verify CEP50 < 5cm.
5. If offset detected, record and apply correction in Nav2 config.
6. Log calibration in digital-twin.

**Pass criteria**: RTK position within 5cm CEP50 of known reference point.

## Calibration schedule summary

| Sensor/Actuator | SOP | Frequency |
|----------------|-----|-----------|
| pH probe | SOP-001 | 90 days |
| EC probe | SOP-002 | 90 days |
| Temperature sensors | SOP-003 | 180 days |
| Flow meters | SOP-004 | 180 days |
| Peristaltic pumps | SOP-005 | 30 days |
| Rover odometry | SOP-006 | 6 months |
| RTK GNSS | SOP-007 | After base move |

Calibration due dates are tracked in digital-twin and surfaced as maintenance reminders in ops-web.
