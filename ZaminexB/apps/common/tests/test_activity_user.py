from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.common.activity import log_activity
from apps.common.models import ActivityLog
from apps.common.thread_locals import set_current_user, clear_current_user

User = get_user_model()


class ActivityLogUserTestCase(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin_test",
            password="pwd",
            role="ADMIN",
        )
        self.consultant_user = User.objects.create_user(
            username="consultant_test",
            password="pwd",
            role="AGENT",
        )

    def tearDown(self):
        clear_current_user()

    def test_log_activity_uses_current_user(self):
        set_current_user(self.admin_user)
        log_activity(
            user=self.consultant_user,
            action="update",
            target_type="property",
            target_id=10,
            description="ویرایش ملک توسط ادمین",
        )
        log = ActivityLog.objects.latest("id")
        self.assertEqual(log.user, self.admin_user)

    def test_log_activity_fallback_when_no_current_user(self):
        clear_current_user()
        log_activity(
            user=self.consultant_user,
            action="update",
            target_type="property",
            target_id=11,
            description="ویرایش ملک در پس‌زمینه",
        )
        log = ActivityLog.objects.latest("id")
        self.assertEqual(log.user, self.consultant_user)

    def test_activity_log_str_with_none_user(self):
        clear_current_user()
        log = ActivityLog.objects.create(
            user=None,
            action="create",
            target_type="system",
            target_id=1,
            description="لاگ بدون کاربر",
        )
        self.assertIn("سیستم", str(log))

