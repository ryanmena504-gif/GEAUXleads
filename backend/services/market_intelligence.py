from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.field_norm import coerce_number, clean_text

log = logging.getLogger("bloodhound.market_intel")


def _extract_year_month(ts: Any) -> Optional[str]:
    if not ts:
        return None
    text = str(ts)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(text[:len(fmt)], fmt)
            return f"{dt.year}-{dt.month:02d}"
        except ValueError:
            continue
    return None


class MarketIntelligence:
    def analyze(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not records:
            return {"error": "No records provided"}

        # Geographic Analysis
        city_counts = Counter()
        for r in records:
            city = clean_text(r.get("city"))
            if city:
                city_counts[city] += 1

        top_cities = [{"city": c, "count": n} for c, n in city_counts.most_common(10)]

        # Permit Velocity
        monthly_permits = Counter()
        for r in records:
            ym = _extract_year_month(r.get("created_time") or r.get("date_discovered"))
            if ym:
                monthly_permits[ym] += 1

        permit_velocity = sorted(
            [{"month": m, "count": c} for m, c in monthly_permits.items()],
            key=lambda x: x["month"],
        )

        months = sorted(monthly_permits.keys(), reverse=True)
        recent = sum(monthly_permits[m] for m in months[:3])
        previous = sum(monthly_permits[m] for m in months[3:6])
        velocity_change = ((recent - previous) / max(previous, 1)) * 100 if previous else None

        # Project Type Distribution
        type_counts = Counter()
        for r in records:
            pt = clean_text(r.get("project_type") or r.get("opportunity_type"))
            if pt:
                type_counts[pt] += 1

        project_types = [
            {"type": t, "count": c, "percentage": round(c / len(records) * 100, 1)}
            for t, c in type_counts.most_common(15)
        ]

        # Revenue Analysis
        values = []
        for r in records:
            v = coerce_number(r.get("estimated_value") or r.get("estimated_job_value") or r.get("construction_value"))
            if v:
                values.append(v)

        total_value = sum(values) if values else None
        avg_value = sum(values) / len(values) if values else None
        median_value = sorted(values)[len(values) // 2] if values else None

        type_revenue = defaultdict(list)
        for r in records:
            pt = clean_text(r.get("project_type") or r.get("opportunity_type")) or "Unknown"
            v = coerce_number(r.get("estimated_value") or r.get("estimated_job_value"))
            if v:
                type_revenue[pt].append(v)

        revenue_by_type = sorted(
            [
                {"type": t, "total": round(sum(vs), 2), "count": len(vs), "average": round(sum(vs) / len(vs), 2)}
                for t, vs in type_revenue.items()
            ],
            key=lambda x: x["total"],
            reverse=True,
        )[:10]

        # Pipeline Health
        status_counts = Counter()
        for r in records:
            s = clean_text(r.get("status")) or "New"
            status_counts[s] += 1

        active = [r for r in records if clean_text(r.get("status")) not in ("Won", "Lost", "Disqualified")]
        pipeline_health = {
            "total_records": len(records),
            "active_records": len(active),
            "win_rate": round(status_counts.get("Won", 0) / max(len(records), 1) * 100, 1),
            "lost_rate": round(status_counts.get("Lost", 0) / max(len(records), 1) * 100, 1),
            "stuck_in_research": status_counts.get("Needs research", 0),
            "ready_to_contact": status_counts.get("Ready", 0),
        }

        # Signal Quality
        enriched = sum(1 for r in records if clean_text(r.get("evidence_summary")))
        with_contact = sum(1 for r in records if clean_text(r.get("phone")) or clean_text(r.get("email")))
        with_address = sum(1 for r in records if clean_text(r.get("project_address") or r.get("address")))

        data_quality = {
            "enrichment_coverage": round(enriched / len(records) * 100, 1),
            "contact_coverage": round(with_contact / len(records) * 100, 1),
            "address_coverage": round(with_address / len(records) * 100, 1),
            "average_fields_populated": self._avg_field_population(records),
        }

        # Hot Zones
        hot_zones = []
        for city, count in city_counts.most_common(5):
            city_records = [r for r in records if clean_text(r.get("city")) == city]
            city_values = [
                coerce_number(r.get("estimated_value") or r.get("estimated_job_value"))
                for r in city_records if coerce_number(r.get("estimated_value") or r.get("estimated_job_value"))
            ]
            hot_zones.append({
                "city": city,
                "permit_count": count,
                "total_estimated_value": round(sum(city_values), 2) if city_values else None,
                "avg_estimated_value": round(sum(city_values) / len(city_values), 2) if city_values else None,
            })
        hot_zones.sort(key=lambda x: x.get("total_estimated_value") or 0, reverse=True)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "geography": {
                "top_cities": top_cities,
                "hot_zones": hot_zones,
                "total_cities": len(city_counts),
            },
            "permit_velocity": {
                "monthly": permit_velocity,
                "recent_3mo": recent,
                "previous_3mo": previous,
                "change_percent": round(velocity_change, 1) if velocity_change is not None else None,
                "trend": "accelerating" if velocity_change and velocity_change > 10 else
                         "decelerating" if velocity_change and velocity_change < -10 else "stable",
            },
            "project_types": project_types,
            "revenue": {
                "total_pipeline_estimate": round(total_value, 2) if total_value else None,
                "average_deal_size": round(avg_value, 2) if avg_value else None,
                "median_deal_size": round(median_value, 2) if median_value else None,
                "by_type": revenue_by_type,
            },
            "pipeline_health": pipeline_health,
            "data_quality": data_quality,
        }

    def _extract_zip(self, address: str) -> Optional[str]:
        match = re.search(r'\d{5}(?:-\d{4})?', address)
        return match.group(0) if match else None

    def _avg_field_population(self, records: List[Dict[str, Any]]) -> float:
        key_fields = ["name", "phone", "email", "project_address", "project_type",
                      "evidence_summary", "estimated_value", "permit_number"]
        total = 0
        for r in records:
            filled = sum(1 for k in key_fields if clean_text(r.get(k)))
            total += filled / len(key_fields)
        return round(total / max(len(records), 1) * 100, 1)


_market_intel: Optional[MarketIntelligence] = None


def get_market_intel() -> MarketIntelligence:
    global _market_intel
    if _market_intel is None:
        _market_intel = MarketIntelligence()
    return _market_intel


def analyze_market(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    return get_market_intel().analyze(records)
