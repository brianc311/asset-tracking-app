import csv
import io
import json
import zipfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.assets.models import Asset

User = get_user_model()

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class ContinuousScanTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="staff", password="x", role=User.Role.STAFF)
        self.client.force_login(self.user)
        self.client.post(
            "/scan/batch/start/",
            {
                "site_name": "__new__",
                "new_site_name": "HQ",
                "product_name": "__new__",
                "new_product_name": "AP",
            },
        )

    def _finish(self, rows, **extra):
        payload = {
            "continuous_mode": "mac",
            "continuous_rows": json.dumps(rows),
            "device_name": "Lobby AP",
            "location": "Rack 1",
            "comments": "Installed today",
        }
        payload.update(extra)
        return self.client.post("/scan/batch/continuous/", payload, follow=True)

    def test_batch_page_offers_continuous_scan(self):
        response = self.client.get("/scan/batch/")
        self.assertContains(response, "Continuous scan")
        self.assertContains(response, reverse("scan:batch_continuous_finish"))
        self.assertContains(response, "Finish")

    def test_mac_scan_saves_each_row_with_shared_fields(self):
        response = self._finish(
            [
                {"mac": "AA:BB:CC:DD:EE:01"},
                {"mac": "AA:BB:CC:DD:EE:02"},
            ]
        )
        self.assertContains(response, "Saved 2 assets.")
        assets = list(Asset.objects.order_by("mac_address"))
        self.assertEqual(len(assets), 2)
        self.assertEqual(assets[0].device_name, "Lobby AP")
        self.assertEqual(assets[0].location, "Rack 1")
        self.assertEqual(assets[0].comments, "Installed today")
        self.assertEqual(assets[0].site_name, "HQ")
        self.assertEqual(assets[0].product_name, "AP")
        self.assertEqual(assets[0].serial_number, "")

    def test_duplicate_inside_the_scan_names_the_row(self):
        response = self._finish(
            [
                {"mac": "AA:BB:CC:DD:EE:11"},
                {"mac": "aa:bb:cc:dd:ee:11"},
            ]
        )
        self.assertContains(response, "Saved 1 assets.")
        self.assertContains(response, "Row 2: MAC AA:BB:CC:DD:EE:11 duplicates row 1.")
        self.assertEqual(Asset.objects.count(), 1)

    def test_duplicate_already_in_the_database_names_the_asset(self):
        Asset.objects.create(
            product_name="Switch",
            site_name="Other",
            serial_number="SN-OLD",
            mac_address="AA:BB:CC:DD:EE:10",
            barcode_value="AT-EXIST-MAC",
            asset_number=15,
        )
        response = self._finish([{"mac": "aa-bb-cc-dd-ee-10"}])
        self.assertContains(response, "Row 1: MAC AA:BB:CC:DD:EE:10 is already on asset #15.")
        self.assertEqual(Asset.objects.filter(mac_address="AA:BB:CC:DD:EE:10").count(), 1)
        self.assertNotContains(response, "Saved 1 assets.")

    def test_shared_serial_on_later_rows_is_reported_as_a_duplicate(self):
        response = self._finish(
            [
                {"mac": "AA:BB:CC:DD:EE:21"},
                {"mac": "AA:BB:CC:DD:EE:22"},
            ],
            shared_serial="SN-SHARED",
        )
        self.assertContains(response, "Saved 1 assets.")
        self.assertContains(response, "Row 2: serial SN-SHARED duplicates row 1.")
        saved = Asset.objects.get(mac_address="AA:BB:CC:DD:EE:21")
        self.assertEqual(saved.serial_number, "SN-SHARED")

    def test_serial_then_mac_pairs_each_device(self):
        response = self._finish(
            [
                {"serial": "SER-1", "mac": "AA:BB:CC:DD:EE:31"},
                {"serial": "SER-2", "mac": "AA:BB:CC:DD:EE:32"},
            ],
            continuous_mode="pair",
        )
        self.assertContains(response, "Saved 2 assets.")
        paired = Asset.objects.get(serial_number="SER-1")
        self.assertEqual(paired.mac_address, "AA:BB:CC:DD:EE:31")
        self.assertEqual(paired.device_name, "Lobby AP")

    def test_invalid_mac_names_the_row_and_saves_the_others(self):
        response = self._finish(
            [
                {"mac": "AA:BB:CC:DD:EE:41"},
                {"mac": "not-a-mac"},
            ]
        )
        self.assertContains(response, "Saved 1 assets.")
        self.assertContains(response, "Row 2: not-a-mac is not a valid MAC address.")
        self.assertTrue(Asset.objects.filter(mac_address="AA:BB:CC:DD:EE:41").exists())

    def test_page_offers_csv_and_excel_downloads(self):
        response = self.client.get("/scan/batch/")
        self.assertContains(response, "Download CSV")
        self.assertContains(response, "Download Excel")
        self.assertContains(response, "/scan/batch/continuous/export/?format=csv")
        self.assertContains(response, "/scan/batch/continuous/export/?format=xlsx")

    def test_csv_and_excel_include_saved_scan_rows(self):
        self._finish(
            [{"mac": "AA:BB:CC:DD:EE:51"}],
            device_name="Front door",
            location="Closet",
            comments="Checked in",
        )
        csv_response = self.client.get("/scan/batch/continuous/export/?format=csv")
        self.assertEqual(csv_response["Content-Disposition"], 'attachment; filename="continuous-batch.csv"')
        rows = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
        self.assertEqual(rows[0][0], "Row")
        self.assertEqual(rows[1][6], "AA:BB:CC:DD:EE:51")
        self.assertIn("Front door", rows[1])
        self.assertIn("Closet", rows[1])
        self.assertIn("Checked in", rows[1])

        excel_response = self.client.get("/scan/batch/continuous/export/?format=xlsx")
        self.assertEqual(excel_response["Content-Disposition"], 'attachment; filename="continuous-batch.xlsx"')
        with zipfile.ZipFile(io.BytesIO(excel_response.content)) as workbook:
            sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("AA:BB:CC:DD:EE:51", sheet)
        self.assertIn("Front door", sheet)
