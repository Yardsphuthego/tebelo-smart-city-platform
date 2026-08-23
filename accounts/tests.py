from django.test import TestCase
from django.urls import reverse

from .models import User


class PhoneAccountTests(TestCase):
    def test_public_navigation_switches_between_login_and_logout(self):
        anonymous = self.client.get(reverse("home"))
        self.assertContains(anonymous, "Sign in")
        self.assertNotContains(anonymous, "public-signout")

        resident = User.objects.create_user(
            phone_number="+26773456789", password="A-strong-resident-pass-2026"
        )
        self.client.force_login(resident)
        authenticated = self.client.get(reverse("home"))
        self.assertContains(authenticated, "Open dashboard")
        self.assertContains(authenticated, "Sign out")
        self.assertNotContains(authenticated, ">Sign in<")

    def test_resident_can_register_with_phone_without_email(self):
        response = self.client.post(
            reverse("register"),
            {
                "first_name": "Naledi",
                "last_name": "Molefe",
                "phone_number": "71 234 567",
                "password1": "A-strong-resident-pass-2026",
                "password2": "A-strong-resident-pass-2026",
                "consent": "on",
            },
        )

        self.assertRedirects(response, reverse("dashboard"))
        user = User.objects.get(phone_number="+26771234567")
        self.assertIsNone(user.email)
        self.assertEqual(user.role, User.Role.RESIDENT)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_resident_can_sign_in_using_local_phone_format(self):
        User.objects.create_user(
            phone_number="+26772345678", password="A-strong-resident-pass-2026"
        )

        response = self.client.post(
            reverse("login"),
            {"username": "72 345 678", "password": "A-strong-resident-pass-2026"},
        )

        self.assertRedirects(response, reverse("dashboard"))

    def test_phone_only_resident_has_safe_display_name(self):
        user = User.objects.create_user(
            phone_number="+26775550123", password="A-strong-resident-pass-2026"
        )

        self.assertEqual(str(user), "+26775550123")

    def test_authority_account_is_routed_to_command_dashboard(self):
        officer = User.objects.create_user(
            email="officer@tebelo.local",
            password="A-strong-authority-pass-2026",
            role=User.Role.OFFICER,
        )
        self.client.force_login(officer)

        self.assertRedirects(
            self.client.get(reverse("dashboard")), reverse("command_dashboard")
        )

    def test_existing_authority_email_login_still_works(self):
        User.objects.create_superuser(
            email="authority@tebelo.local", password="A-strong-authority-pass-2026"
        )

        response = self.client.post(
            reverse("login"),
            {
                "username": "authority@tebelo.local",
                "password": "A-strong-authority-pass-2026",
            },
        )

        self.assertRedirects(
            response,
            reverse("dashboard"),
            target_status_code=302,
        )

    def test_super_admin_dashboard_routes_to_platform_administration(self):
        admin = User.objects.create_superuser(
            email="admin@tebelo.local", password="A-strong-authority-pass-2026"
        )
        self.client.force_login(admin)

        self.assertRedirects(
            self.client.get(reverse("dashboard")), reverse("admin:index")
        )
