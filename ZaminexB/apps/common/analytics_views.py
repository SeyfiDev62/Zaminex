import datetime
from collections import Counter
from decimal import Decimal

from django.db.models import Avg, Q
from django.utils import timezone

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import ConsultantProfile, UserRole
from apps.followups.models import FollowUp
from apps.listings.models import Listing
from apps.properties.models import Property
from apps.tasks.models import Task

from .metrics import (
    build_neighborhood_price_per_sqm_map,
    channel_marketing_summary,
    consultant_avg_deal_probability,
    consultant_performance_metrics,
    consultant_tasks_overdue_count,
    listing_marketing_metrics,
    property_market_metrics,
    annotate_effective_prices,
)


def _month_start(d: datetime.date, offset: int) -> datetime.date:
    """First day of the month `offset` months from `d` (offset may be negative)."""
    m = d.month - 1 + offset
    y = d.year + m // 12
    return datetime.date(y, m % 12 + 1, 1)


PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]


def _get_monthly_revenue():
    """Calculate monthly revenue for last 6 months based on SOLD properties.

    Revenue is sum of effective sale prices of properties sold in each month,
    converted to Billion Toman for chart display.
    """
    today = timezone.now().date()

    # Buckets for last 6 months
    buckets = []
    for i in range(-5, 1):
        start = _month_start(today, i)
        end = _month_start(today, i + 1)
        persian_idx = (start.month - 1) % 12
        persian_name = PERSIAN_MONTHS[persian_idx]
        buckets.append({"start": start, "end": end, "label": persian_name, "start_date": start})

    # Get all SOLD properties updated in last 6 months
    start_all = buckets[0]["start"]
    sold_qs = Property.objects.filter(
        status=Property.Status.SOLD,
        updated_at__gte=timezone.make_aware(datetime.datetime.combine(start_all, datetime.time.min))
    ).select_related("property_type_ref")

    sold_ids = list(sold_qs.values_list("id", flat=True))
    price_map = annotate_effective_prices(sold_ids)
    sold_with_dates = list(sold_qs.values("id", "updated_at", "price"))

    monthly_data = []
    for b in buckets:
        bucket_sum = Decimal(0)
        bucket_count = 0
        for row in sold_with_dates:
            upd = row["updated_at"]
            if upd is None:
                continue
            upd_date = upd.date() if hasattr(upd, "date") else upd
            if b["start"] <= upd_date < b["end"]:
                pid = row["id"]
                price = price_map.get(pid, row["price"])
                if price is not None:
                    bucket_sum += Decimal(str(price))
                    bucket_count += 1
        revenue_billion = float(bucket_sum / Decimal("1000000000")) if bucket_sum else 0
        revenue_billion = round(revenue_billion, 1)
        monthly_data.append({
            "month": b["label"],
            "revenue": revenue_billion,
            "count": bucket_count,
            "total": int(bucket_sum) if bucket_sum else 0,
        })

    return monthly_data


def _get_property_composition():
    """Dynamic property composition by type: count, percentage, Persian name."""
    qs = Property.active_objects.select_related("property_type_ref").all()

    type_counts: dict[str, int] = {}
    legacy_map = {
        "APARTMENT": "آپارتمان",
        "VILLA": "ویلا",
        "TOWNHOUSE": "خانه ویلایی",
        "STUDIO": "استودیو",
        "PENTHOUSE": "پنت‌هاوس",
        "COMMERCIAL": "تجاری",
        "OFFICE": "اداری",
        "SHOP": "مغازه",
        "LAND": "زمین",
        "OTHER": "سایر",
    }

    for prop in qs:
        if prop.property_type_ref:
            name = prop.property_type_ref.display_name
        else:
            name = legacy_map.get(prop.property_type, prop.property_type or "سایر")
        type_counts[name] = type_counts.get(name, 0) + 1

    total = sum(type_counts.values()) or 1
    sorted_types = sorted(type_counts.items(), key=lambda x: -x[1])

    result = []
    for name, count in sorted_types:
        pct = round(count / total * 100, 1)
        result.append({
            "name": name,
            "value": count,
            "count": count,
            "percentage": pct,
            "label": f"{name} {pct}٪",
        })

    return result


def consultant_detail_report(profile) -> dict:
    """Drill-down analytics for a single consultant profile.

    All metrics are scoped to the consultant's linked user account:
      - tasks: assigned to the consultant
      - follow-ups: owned by the consultant (non-archived)
      - listings: created by or assigned to the consultant
      - properties: properties the consultant is responsible for
    """
    user = profile.user
    now = timezone.now()
    today = now.date()
    since_30 = now - datetime.timedelta(days=30)

    tasks_qs = Task.objects.filter(assigned_to=user).exclude(
        status=Task.Status.CANCELLED
    )
    followups_qs = FollowUp.objects.filter(consultant=user, is_archived=False)
    listings_qs = Listing.objects.filter(Q(created_by=user) | Q(assigned_to=user))
    properties_count = Property.objects.filter(consultant=user).count()

    # ---- KPIs --------------------------------------------------------------
    open_tasks = tasks_qs.exclude(status=Task.Status.COMPLETED)
    completed_tasks = tasks_qs.filter(status=Task.Status.COMPLETED)
    total_tasks = tasks_qs.count()
    completed_count = completed_tasks.count()
    active_listings = listings_qs.filter(status=Listing.Status.ACTIVE).count()
    followup_count = followups_qs.count()
    overdue_count = consultant_tasks_overdue_count(user)
    avg_probability = consultant_avg_deal_probability(user)
    completion_rate = (
        round(completed_count / total_tasks * 100) if total_tasks else None
    )

    # ---- Monthly activity (last 6 months, Jalali label built client-side) --
    buckets = []
    for i in range(-5, 1):
        start = _month_start(today, i)
        end = _month_start(today, i + 1)
        buckets.append({"month": start.isoformat(), "start": start, "end": end})

    def _in_bucket(dt, b) -> bool:
        if dt is None:
            return False
        d = dt.date() if isinstance(dt, datetime.datetime) else dt
        return b["start"] <= d < b["end"]

    monthly = []
    for b in buckets:
        monthly.append(
            {
                "month": b["month"],
                "tasksCompleted": sum(
                    1 for t in completed_tasks if _in_bucket(t.completed_at, b)
                ),
                "followups": sum(
                    1 for f in followups_qs if _in_bucket(f.created_at, b)
                ),
                "listings": sum(
                    1 for l in listings_qs if _in_bucket(l.created_at, b)
                ),
            }
        )

    # ---- Tasks by status ----------------------------------------------------
    status_counts = Counter(tasks_qs.values_list("status", flat=True))
    tasks_by_status = [
        {"status": status, "count": cnt}
        for status, cnt in sorted(status_counts.items(), key=lambda x: -x[1])
    ]

    # ---- Follow-ups by type --------------------------------------------------
    followups_by_type = []
    types_seen = Counter(followups_qs.values_list("follow_up_type", flat=True))
    avg_map = {
        row["follow_up_type"]: round(row["avg"], 1)
        for row in followups_qs.exclude(probability__isnull=True)
        .values("follow_up_type")
        .annotate(avg=Avg("probability"))
    }
    for fu_type, cnt in sorted(types_seen.items(), key=lambda x: -x[1]):
        followups_by_type.append(
            {"type": fu_type, "count": cnt, "avgProbability": avg_map.get(fu_type)}
        )

    # ---- Listings by publish channel ----------------------------------------
    channel_counts = Counter(listings_qs.values_list("publish_channel", flat=True))
    listings_by_channel = [
        {"channel": ch or "WEBSITE", "count": cnt}
        for ch, cnt in sorted(channel_counts.items(), key=lambda x: -x[1])
    ]

    # ---- Performance profile (radar, 0..100 per axis) ------------------------
    open_count = open_tasks.count()
    punctuality = (
        max(0, round((1 - overdue_count / open_count) * 100)) if open_count else 100
    )
    recent_activity = (
        followups_qs.filter(created_at__gte=since_30).count()
        + completed_tasks.filter(completed_at__gte=since_30).count()
    )
    performance_profile = [
        {"metric": "تکمیل وظایف", "score": completion_rate if completion_rate is not None else 0},
        {"metric": "انجام به‌موقع", "score": punctuality},
        {"metric": "کیفیت پیگیری", "score": round(avg_probability) if avg_probability is not None else 0},
        {
            "metric": "پوشش بازاریابی",
            "score": min(100, round(active_listings / properties_count * 100)) if properties_count else 0,
        },
        {"metric": "تعامل اخیر", "score": min(100, round(recent_activity / 20 * 100))},
    ]

    return {
        "consultant": {
            "id": profile.pk,
            "fullName": profile.full_name,
            "branch": profile.branch,
            "userId": profile.user_id,
        },
        "kpis": {
            "propertyCount": properties_count,
            "activeListings": active_listings,
            "openTasks": open_count,
            "completedTasks": completed_count,
            "followupCount": followup_count,
            "avgDealProbability": avg_probability,
            "tasksOverdueCount": overdue_count,
            "completionRate": completion_rate,
        },
        "charts": {
            "monthlyActivity": monthly,
            "tasksByStatus": tasks_by_status,
            "followupsByType": followups_by_type,
            "listingsByChannel": listings_by_channel,
            "performanceProfile": performance_profile,
        },
        "meta": {"generatedAt": now.isoformat()},
    }


class ConsultantDetailAnalyticsView(APIView):
    """Detailed analytics for a single consultant profile.

    GET /common/api/analytics/consultants/<pk>/
    Admin: any consultant. Agent: only their own profile.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        profile = (
            ConsultantProfile.objects.select_related("user")
            .filter(pk=pk, user__role=UserRole.AGENT)
            .first()
        )
        if profile is None:
            return Response({"error": "مشاور یافت نشد"}, status=404)
        if (
            getattr(request.user, "role", "") != "ADMIN"
            and profile.user_id != request.user.pk
        ):
            return Response(
                {"error": "شما به گزارش این مشاور دسترسی ندارید."}, status=403
            )
        return Response(consultant_detail_report(profile))


class ConsultantAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profiles = ConsultantProfile.objects.select_related("user").filter(
            is_active=True, user__role=UserRole.AGENT
        )
        rows = []
        for profile in profiles:
            base = {
                "id": profile.id,
                "fullName": profile.full_name,
                "branch": profile.branch,
                "userId": profile.user_id,
            }
            base.update(consultant_performance_metrics(profile))
            rows.append(base)
        rows.sort(key=lambda r: (-(r.get("avgDealProbability") or 0), r.get("tasksOverdueCount", 0)))
        return Response({"consultants": rows})


class PropertyAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        qs = Property.objects.prefetch_related("images")
        if getattr(user, "role", "") != "ADMIN":
            qs = qs.filter(consultant=user)
        properties = list(qs.order_by("-created_at"))
        neighborhood_avg = build_neighborhood_price_per_sqm_map(properties)
        rows = []
        for prop in properties:
            row = {"id": prop.id, "title": prop.title, "neighborhood": prop.neighborhood}
            row.update(property_market_metrics(prop, neighborhood_avg))
            rows.append(row)
        return Response({"properties": rows})


class ListingAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        qs = Listing.objects.select_related("property", "created_by", "assigned_to").prefetch_related(
            "property__images"
        )
        if getattr(user, "role", "") != "ADMIN":
            from django.db.models import Q

            qs = qs.filter(Q(created_by=user) | Q(assigned_to=user))
        listings = list(qs.order_by("-created_at"))
        rows = [listing_marketing_metrics(lst) for lst in listings]
        channels = channel_marketing_summary(listings)
        return Response({"listings": rows, "channels": channels})


class AnalyticsDashboardView(APIView):
    """Compact bundle for reports / admin dashboard widgets."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        consultant_view = ConsultantAnalyticsView()
        consultant_view.request = request
        property_view = PropertyAnalyticsView()
        property_view.request = request
        listing_view = ListingAnalyticsView()
        listing_view.request = request

        c_data = consultant_view.get(request).data
        p_data = property_view.get(request).data
        l_data = listing_view.get(request).data

        top_consultants = (c_data.get("consultants") or [])[:5]
        hot_properties = sorted(
            p_data.get("properties") or [],
            key=lambda x: x.get("engagementHeatScore") or 0,
            reverse=True,
        )[:5]

        # Dynamic charts for admin dashboard
        revenue_monthly = _get_monthly_revenue()
        property_composition = _get_property_composition()

        return Response(
            {
                "topConsultants": top_consultants,
                "hotProperties": hot_properties,
                "channelSummary": l_data.get("channels") or [],
                "consultantCount": len(c_data.get("consultants") or []),
                "propertyCount": len(p_data.get("properties") or []),
                "listingCount": len(l_data.get("listings") or []),
                "revenueMonthly": revenue_monthly,
                "propertyComposition": property_composition,
            }
        )
