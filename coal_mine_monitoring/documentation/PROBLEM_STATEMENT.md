# Smart India Hackathon (SIH) — Problem Statement 26025

## Official Problem Definition

| Parameter | Official Record |
| :--- | :--- |
| **Problem Statement ID** | **26025** |
| **Problem Statement Title** | **Development of an AI-enabled Low Cost Real Time Mine Subsidence Monitoring, Prediction and Early Warning System for Underground Coal Mines in India** |
| **Organization** | Ministry of Coal |
| **Department** | Coal India Limited (CIL) |
| **Category** | Hardware |
| **Theme** | Smart Automation / Mining Safety |

---

## 1. Background and Context

Surface subsidence caused by underground coal extraction and open-cast highwall de-stressing poses grave operational and safety hazards across Indian coalfields (including Jharia, Raniganj, Singrauli, Korba, and Neyveli). Progressive strata movement endangers:
- Public infrastructure, arterial haul roads, railway corridors, and water bodies.
- Local mining communities and surface installations.
- Heavy earth-moving machinery (HEMM) operating along open-cast pit benches.

Historically, Indian coal mining operations have relied on:
1. **Periodic Manual Surveys**: Prisms, total stations, and dumpy levels measured on weekly or monthly cycles.
2. **Post-Facto Damage Assessments**: Crack inspections performed after ground rupture has already initiated.
3. **Expensive Satellite InSAR / Terrestrial LiDAR**: High capital expense, multi-day satellite revisit intervals, and susceptibility to atmospheric and dense vegetation clutter.

These conventional methods fail to provide continuous, real-time warning before critical ground shear and catastrophic slope collapse take place.

---

## 2. Problem Statement Objective

There is an imperative need for an indigenous, cost-effective, intelligent, and real-time monitoring and early warning system capable of detecting micro-deformation signatures at the millimetric scale, enabling proactive risk mitigation prior to slope failure.

The system must be deployable across active Indian open-cast and underground coalfields, adhering to Directorate General of Mines Safety (DGMS) regulatory standards and advancing the national vision of *Atmanirbhar Bharat* and sustainable mining safety.

---

## 3. Scope of the Solution

The solution develops an integrated IoT and AI-driven geotechnical safety platform based on a distributed surface mesh/star sensor network deployed above active mining panels:

### A. Edge IoT Sensor Network
- Deployment of low-cost, robust, autonomous sensor nodes across highwall benches and subsidence-prone surface zones.
- Sensing parameters:
  - High-precision triaxial inclination and tilt ($\theta_x, \theta_y, \theta_{\text{total}}$).
  - High-frequency dynamic vibration and peak impact acceleration ($g$).
  - Relative displacement between nodes and subsidence perimeter.
  - Surface crack progression and rate of strain.

### B. Industrial Wireless Communication
- Autonomous sub-gigahertz LoRa (433 MHz) wireless telemetry enabling long-range, line-of-sight and non-line-of-sight propagation across deep pit topologies without cellular network or internet dependency.

### C. Geotechnical AI & Signal Processing Engine
- Signal filtering using multi-stage Kalman filters to eliminate environmental noise (wind gusts, mining shovel vibrations, vehicle transits).
- Relative spatial coordinate tracking via Classical Multidimensional Scaling (MDS).
- Continuous computation of the geotechnical Factor of Safety ($\text{FoS}$).
- Machine learning anomaly classification (XGBoost) trained on empirical ground deformation progression (Saito's Creep Theory) to eliminate false positives.

### D. Centralized Command Center & Early Warning
- Dual-mode interactive GIS visual dashboard (Operator Command Center & Engineering Diagnostics).
- Sub-50ms low-latency USB serial edge gateway bridge.
- Multi-tier alert mechanisms:
  - **Normal Baseline**: Stable ($\text{FoS} \geq 1.50$).
  - **Warning Advisory**: Accelerating creep ($1.00 \leq \text{FoS} < 1.50$).
  - **Critical Failure Threat**: Imminent runaway collapse ($\text{FoS} < 1.00$) with automated acoustic sirens, visual strobes, and evacuation directives.

---

## 4. Key Differentiators & Innovation Benchmarks

1. **Sub-Gigahertz LoRa Mesh Architecture**: Operates independently of mine cellular infrastructure or satellite availability.
2. **Hybrid Physics + AI Safety Model**: Merges Terzaghi limit-equilibrium slope stability physics with XGBoost gradient boosting to guarantee zero nuisance alarms.
3. **Sub-50ms Edge Telemetry**: Direct USB serial streaming to pit-top emergency management systems with zero cloud dependence.
4. **Low Capital Expenditure (CapEx)**: Built on accessible industrial microcontrollers, reducing node deployment cost by $>85\%$ compared to imported slope stability radar (SSR).
5. **Made in India (Atmanirbhar Bharat)**: Indigenous firmware, edge architecture, and open geotechnical modeling tailored for Indian geo-mining conditions.
