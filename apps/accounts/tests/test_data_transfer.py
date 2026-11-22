import io
import json
import tempfile
import zipfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.assets.models import Asset
from apps.assets.transfer import export_assets, import_assets

User = get_user_model()

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def _zip_bytes(rows, photos=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"kind": "asset-tracking-desktop", "version": 1}),
        )
        archive.writestr("assets.json", json.dumps(rows))
        for name, content in (photos or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


@override_settings(STORAGES=TEST_STORAGES)
class DataTransferPageTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="root",
            password="x",
            role=User.Role.SUPER_USER,
        )
        self.staff = User.objects.create_user(
            username="staff",
            password="x",
            role=User.Role.STAFF,
        )

    def test_superuser_sees_export_and_import_on_both_pages(self):
        self.client.force_login(self.superuser)
        for url in (reverse("accounts:security_logs"), reverse("branding:console")):
            response = self.client.get(url)
            self.assertContains(response, "Export data")
            self.assertContains(response, "Import data")
            self.assertContains(response, reverse("accounts:export_data"))
            self.assertContains(response, reverse("accounts:import_data"))

    def test_staff_cannot_export(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("accounts:export_data"))
        self.assertRedirects(response, reverse("accounts:dashboard"))


@override_settings(STORAGES=TEST_STORAGES)
class DataTransferMergeTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.tmp.name)
        self.settings_override.enable()
        self.superuser = User.objects.create_user(
            username="root",
            password="x",
            role=User.Role.SUPER_USER,
        )
        self.client.force_login(self.superuser)

    def tearDown(self):
        self.settings_override.disable()
        self.tmp.cleanup()

    def _upload(self, payload, next_url=None):
        return self.client.post(
            reverse("accounts:import_data"),
            {
                "import_file": SimpleUploadedFile(
                    "asset-tracking-export.zip",
                    payload,
                    content_type="application/zip",
                ),
                "next": next_url or reverse("accounts:security_logs"),
            },
        )

    def test_export_and_import_round_trip_keeps_barcode_and_photo(self):
        asset = Asset.objects.create(
            product_name="Switch",
            barcode_value="AT-ROUND01",
            serial_number="SN-ROUND",
            asset_number=7,
        )
        asset.photo.save("switch.jpg", ContentFile(b"photo-bytes"), save=True)
        payload = export_assets()
        asset.delete()

        result = import_assets(io.BytesIO(payload))
        restored = Asset.objects.get(barcode_value="AT-ROUND01")
        self.assertEqual(result.added, 1)
        self.assertEqual(restored.asset_number, 7)
        self.assertEqual(restored.serial_number, "SN-ROUND")
        self.assertEqual(Path(self.tmp.name, restored.photo.name).read_bytes(), b"photo-bytes")

    def test_import_skips_barcode_serial_and_mac_duplicates(self):
        Asset.objects.create(
            product_name="Existing",
            barcode_value="AT-EXIST",
            serial_number="SN-EXIST",
            mac_address="AA:BB:CC:DD:EE:FF",
            asset_number=1,
        )
        payload = _zip_bytes(
            [
                {
                    "uuid": "11111111-1111-1111-1111-111111111111",
                    "asset_number": 1,
                    "barcode_value": "AT-EXIST",
                    "product_name": "Same barcode",
                },
                {
                    "uuid": "22222222-2222-2222-2222-222222222222",
                    "asset_number": 2,
                    "barcode_value": "AT-NEWSERIAL",
                    "serial_number": "sn-exist",
                    "product_name": "Same serial",
                },
                {
                    "uuid": "33333333-3333-3333-3333-333333333333",
                    "asset_number": 3,
                    "barcode_value": "AT-NEWMAC",
                    "mac_address": "aa-bb-cc-dd-ee-ff",
                    "product_name": "Same mac",
                },
                {
                    "uuid": "44444444-4444-4444-4444-444444444444",
                    "asset_number": 1,
                    "barcode_value": "AT-RENUMBER",
                    "product_name": "New device",
                },
            ]
        )
        response = self.client.post(
            reverse("accounts:import_data"),
            {
                "import_file": SimpleUploadedFile(
                    "asset-tracking-export.zip",
                    payload,
                    content_type="application/zip",
                ),
                "next": reverse("accounts:security_logs"),
            },
            follow=True,
        )
        self.assertContains(response, "Added 1 assets. Skipped 3 already on this copy.")
        created = Asset.objects.get(barcode_value="AT-RENUMBER")
        self.assertNotEqual(created.asset_number, 1)
        self.assertEqual(Asset.objects.count(), 2)
        follow = self.client.get(reverse("accounts:security_logs"))
        self.assertContains(follow, "Export data")
        self.assertContains(follow, "Import data")

    def test_second_import_adds_nothing(self):
        payload = _zip_bytes(
            [
                {
                    "uuid": "55555555-5555-5555-5555-555555555555",
                    "barcode_value": "AT-ONCE",
                    "product_name": "Once",
                }
            ]
        )
        first = import_assets(io.BytesIO(payload))
        second = import_assets(io.BytesIO(payload))
        self.assertEqual(first.added, 1)
        self.assertEqual(second.added, 0)
        self.assertEqual(second.skipped, 1)

    def test_rejects_a_file_that_is_not_an_export(self):
        response = self._upload(b"not-a-zip")
        follow = self.client.get(response["Location"])
        self.assertContains(follow, "That file is not an Asset Tracking export.")
