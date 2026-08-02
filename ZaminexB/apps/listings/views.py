from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import admin_required
from apps.properties.models import Property
from .models import Listing
from .serializers import ListingSerializer
from apps.common.pagination import StandardResultsSetPagination

class ListingViewSet(viewsets.ModelViewSet):
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        if user.role == "ADMIN":
            qs = Listing.objects.all().select_related(
                'property', 'created_by', 'assigned_to', 'deal_type'
            ).prefetch_related('property__images')
        else:
            qs = Listing.objects.filter(
                Q(created_by=user) | Q(assigned_to=user)
            ).select_related('property', 'created_by', 'assigned_to', 'deal_type').prefetch_related(
                'property__images'
            )

        # --- common filters (server-side pagination) ----------------------
        # Search by title
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(id__icontains=q) |
                Q(property__title__icontains=q)
            )

        # Status filter (ACTIVE, DRAFT, etc)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status__iexact=status_param)

        # Consultant / assigned_to filter (admin only)
        consultant = self.request.query_params.get("consultant") or self.request.query_params.get("assigned_to")
        if consultant and user.role == "ADMIN":
            if str(consultant).isdigit():
                qs = qs.filter(assigned_to_id=consultant)
            else:
                qs = qs.filter(assigned_to__username__icontains=consultant)

        # Property filter
        prop = self.request.query_params.get("property")
        if prop:
            if str(prop).isdigit():
                qs = qs.filter(property_id=prop)
            else:
                qs = qs.filter(property__title__icontains=prop)

        # Deal type filter
        deal_type = self.request.query_params.get("dealType") or self.request.query_params.get("deal_type")
        if deal_type:
            if str(deal_type).isdigit():
                qs = qs.filter(deal_type_id=deal_type)
            else:
                qs = qs.filter(
                    Q(deal_type__display_name__iexact=deal_type) |
                    Q(deal_type__name__iexact=deal_type) |
                    Q(deal_type__display_name__icontains=deal_type)
                )

        # Price range filters
        # Rent (monthly_rent)
        rent_min = self.request.query_params.get("rentMin")
        rent_max = self.request.query_params.get("rentMax")
        if rent_min:
            qs = qs.filter(monthly_rent__gte=rent_min)
        if rent_max:
            qs = qs.filter(monthly_rent__lte=rent_max)

        # Deposit / ودیعه
        deposit_min = self.request.query_params.get("depositMin")
        deposit_max = self.request.query_params.get("depositMax")
        if deposit_min:
            qs = qs.filter(deposit__gte=deposit_min)
        if deposit_max:
            qs = qs.filter(deposit__lte=deposit_max)

        # Sale / Rahn - فروش و رهن یکی حساب می‌شود: sale_price یا deposit
        sale_min = self.request.query_params.get("saleMin")
        sale_max = self.request.query_params.get("saleMax")
        if sale_min or sale_max:
            if sale_min and sale_max:
                qs = qs.filter(
                    Q(sale_price__gte=sale_min, sale_price__lte=sale_max) |
                    Q(deposit__gte=sale_min, deposit__lte=sale_max)
                )
            elif sale_min:
                qs = qs.filter(
                    Q(sale_price__gte=sale_min) |
                    Q(deposit__gte=sale_min)
                )
            elif sale_max:
                qs = qs.filter(
                    Q(sale_price__lte=sale_max) |
                    Q(deposit__lte=sale_max)
                )

        return qs.order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if request.user.role != "ADMIN":
            return Response({"detail": "فقط مدیران می‌توانند آگهی‌ها را تأیید کنند."}, status=status.HTTP_403_FORBIDDEN)
        listing = self.get_object()
        listing.status = Listing.Status.ACTIVE
        listing.save(update_fields=['status', 'updated_at'])
        return Response(ListingSerializer(listing).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        if request.user.role != "ADMIN":
            return Response({"detail": "فقط مدیران می‌توانند آگهی‌ها را رد کنند."}, status=status.HTTP_403_FORBIDDEN)
        listing = self.get_object()
        listing.status = Listing.Status.DRAFT
        listing.save(update_fields=['status', 'updated_at'])
        return Response(ListingSerializer(listing).data)

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        listing = self.get_object()
        if request.user.role != "ADMIN" and listing.created_by != request.user:
            return Response({"detail": "شما اجازه انجام این عملیات را ندارید."}, status=status.HTTP_403_FORBIDDEN)
            
        if listing.status == Listing.Status.ACTIVE:
            listing.status = Listing.Status.PAUSED
        elif listing.status == Listing.Status.PAUSED:
            listing.status = Listing.Status.ACTIVE
        else:
            return Response({"detail": "آگهی باید فعال یا متوقف‌شده باشد."}, status=status.HTTP_400_BAD_REQUEST)
            
        listing.save(update_fields=['status', 'updated_at'])
        return Response(ListingSerializer(listing).data)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        listing = self.get_object()
        if request.user.role != "ADMIN" and listing.created_by != request.user:
            return Response({"detail": "شما اجازه انجام این عملیات را ندارید."}, status=status.HTTP_403_FORBIDDEN)
        listing.status = Listing.Status.ARCHIVED
        listing.save(update_fields=['status', 'updated_at'])
        return Response(ListingSerializer(listing).data)

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        listing = self.get_object()
        if request.user.role != "ADMIN" and listing.created_by != request.user:
            return Response({"detail": "شما اجازه انجام این عملیات را ندارید."}, status=status.HTTP_403_FORBIDDEN)
        if listing.status != Listing.Status.ARCHIVED:
            return Response({"detail": "آگهی باید بایگانی‌شده باشد."}, status=status.HTTP_400_BAD_REQUEST)
        listing.status = Listing.Status.ACTIVE
        listing.save(update_fields=['status', 'updated_at'])
        return Response(ListingSerializer(listing).data)


@login_required
def listing_list(request):
    return render(request, "listings/listing_list.html", {"listing_props": {}})
