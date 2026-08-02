from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import ConsultantProfile, UserRole
from apps.common.metrics import (
    content_richness_score,
    delegation_indicator,
    effective_exposure_days,
    geo_precision_flag,
    is_burned_listing,
    price_deviation_index,
    price_per_sqm,
    property_market_metrics,
    spatial_density_ratio,
)
from apps.followups.models import FollowUp
from apps.listings.models import Listing
from apps.properties.models import Property
from apps.tasks.models import Task

User = get_user_model()


class MetricsUnitTests(TestCase):
    def test_price_per_sqm_and_spatial_density(self):
        self.assertIsNone(price_per_sqm(100, 0))
        self.assertEqual(price_per_sqm(200_000_000, 100), 2_000_000.0)
        self.assertIsNone(spatial_density_ratio(3, 0))
        self.assertEqual(spatial_density_ratio(3, 80), 0.0375)

    def test_geo_precision_flag(self):
        self.assertFalse(geo_precision_flag(None, None))
        self.assertFalse(geo_precision_flag(0, 0))
        self.assertTrue(geo_precision_flag(Decimal("35.7"), Decimal("51.4")))

    def test_price_deviation_index(self):
        agent = User.objects.create_user(username="a1", password="pass12345", role=UserRole.AGENT)
        p1 = Property.objects.create(
            title="P1",
            internal_code="IC1",
            consultant=agent,
            property_type=Property.PropertyType.APARTMENT,
            deal_type=Property.DealType.SALE,
            price=120_000_000,
            area=100,
            rooms=2,
            address="addr",
            neighborhood="N1",
        )
        Property.objects.create(
            title="P2",
            internal_code="IC2",
            consultant=agent,
            property_type=Property.PropertyType.APARTMENT,
            deal_type=Property.DealType.SALE,
            price=80_000_000,
            area=100,
            rooms=2,
            address="addr",
            neighborhood="N1",
        )
        idx = price_deviation_index(p1)
        self.assertIsNotNone(idx)
        self.assertGreater(idx, 0)

    def test_delegation_and_exposure(self):
        admin = User.objects.create_user(username="adm", password="pass12345", role=UserRole.ADMIN)
        agent = User.objects.create_user(username="ag", password="pass12345", role=UserRole.AGENT)
        prop = Property.objects.create(
            title="P",
            internal_code="IC3",
            consultant=agent,
            property_type=Property.PropertyType.APARTMENT,
            deal_type=Property.DealType.SALE,
            price=1,
            area=100,
            address="a",
            neighborhood="N",
        )
        start = timezone.now() - timedelta(days=10)
        listing = Listing.objects.create(
            property=prop,
            title="L",
            publish_channel=Listing.PublishChannel.WEBSITE,
            created_by=admin,
            assigned_to=agent,
            start_date=start,
        )
        self.assertEqual(delegation_indicator(listing), "DELEGATED")
        self.assertEqual(effective_exposure_days(listing), 10)

        solo = Listing.objects.create(
            property=prop,
            title="L2",
            publish_channel=Listing.PublishChannel.WEBSITE,
            created_by=agent,
            assigned_to=agent,
            start_date=start,
        )
        self.assertEqual(delegation_indicator(solo), "SELF_MANAGED")

    def test_burned_and_content_score(self):
        agent = User.objects.create_user(username="ag2", password="pass12345", role=UserRole.AGENT)
        prop = Property.objects.create(
            title="P",
            internal_code="IC4",
            consultant=agent,
            property_type=Property.PropertyType.APARTMENT,
            deal_type=Property.DealType.SALE,
            price=1,
            area=100,
            address="a",
            neighborhood="N",
        )
        listing = Listing.objects.create(
            property=prop,
            title="Long title",
            description="x" * 600,
            publish_channel=Listing.PublishChannel.INSTAGRAM,
            created_by=agent,
            status=Listing.Status.EXPIRED,
        )
        self.assertTrue(is_burned_listing(listing))
        self.assertGreaterEqual(content_richness_score(listing, images_count=6), 4)

    def test_property_market_metrics_engagement(self):
        agent = User.objects.create_user(username="ag3", password="pass12345", role=UserRole.AGENT)
        prop = Property.objects.create(
            title="P",
            internal_code="IC5",
            consultant=agent,
            property_type=Property.PropertyType.APARTMENT,
            deal_type=Property.DealType.SALE,
            price=100_000_000,
            area=50,
            rooms=2,
            address="a",
            neighborhood="N",
            latitude=Decimal("36.5"),
            longitude=Decimal("52.5"),
        )
        FollowUp.objects.create(
            title="f",
            consultant=agent,
            property=prop,
            contact_name="c",
            probability=80,
        )
        Task.objects.create(
            title="visit",
            assigned_to=agent,
            created_by=agent,
            property=prop,
            due_date=date.today() + timedelta(days=1),
            task_type=Task.TaskType.VIEWING,
        )
        metrics = property_market_metrics(prop)
        self.assertEqual(metrics["pricePerSqm"], 2_000_000.0)
        self.assertTrue(metrics["geoPrecisionFlag"])
        self.assertGreaterEqual(metrics["engagementHeatScore"], 4)


class AnalyticsAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin_metrics",
            password="pass12345",
            role=UserRole.ADMIN,
        )
        self.agent = User.objects.create_user(
            username="agent_metrics",
            password="pass12345",
            role=UserRole.AGENT,
        )
        ConsultantProfile.objects.create(
            user=self.agent,
            full_name="Agent One",
            branch="Central",
            hired_at=date.today() - timedelta(days=100),
        )
        self.prop = Property.objects.create(
            title="Test Property",
            internal_code="M-001",
            consultant=self.agent,
            property_type=Property.PropertyType.APARTMENT,
            deal_type=Property.DealType.SALE,
            price=500_000_000,
            area=100,
            rooms=3,
            address="Test address",
            neighborhood="Saadat",
        )
        self.listing = Listing.objects.create(
            property=self.prop,
            title="Listing",
            publish_channel=Listing.PublishChannel.WEBSITE,
            created_by=self.agent,
            assigned_to=self.agent,
            start_date=timezone.now() - timedelta(days=5),
        )

    def test_analytics_endpoints_require_auth(self):
        for path in [
            "/common/api/analytics/consultants/",
            "/common/api/analytics/properties/",
            "/common/api/analytics/listings/",
            "/common/api/analytics/dashboard/",
        ]:
            res = self.client.get(path)
            self.assertIn(res.status_code, [401, 403])

    def test_analytics_dashboard_admin(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/common/api/analytics/dashboard/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("topConsultants", data)
        self.assertIn("hotProperties", data)
        self.assertGreaterEqual(data["propertyCount"], 1)

    def test_property_api_includes_metrics(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/properties/api/properties/")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        if isinstance(items, dict):
            items = items.get("results", [])
        self.assertTrue(any("pricePerSqm" in p for p in items))

    def test_listing_api_includes_metrics(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/listings/api/listings/")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        if isinstance(items, dict):
            items = items.get("results", [])
        self.assertTrue(any("contentRichnessScore" in item for item in items))
