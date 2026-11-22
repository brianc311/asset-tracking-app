import io
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from apps.assets.mac import normalize_mac
from apps.assets.models import Asset

EXPORT_KIND = "asset-tracking-desktop"
EXPORT_VERSION = 1
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


class TransferError(Exception):
    pass


@dataclass
class ImportResult:
    added: int
    skipped: int


def export_assets() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        payloads = []
        for asset in Asset.objects.all().order_by("asset_number", "pk"):
            payloads.append(_asset_payload(asset))
            if not asset.photo:
                continue
            photo_path = Path(settings.MEDIA_ROOT) / asset.photo.name
            if photo_path.is_file():
                archive.write(photo_path, arcname=f"media/{asset.photo.name}")
        archive.writestr(
            "manifest.json",
            json.dumps({"kind": EXPORT_KIND, "version": EXPORT_VERSION}),
        )
        archive.writestr("assets.json", json.dumps(payloads))
    return buffer.getvalue()


def import_assets(upload) -> ImportResult:
    size = getattr(upload, "size", None)
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise TransferError("That file is too large.")
    payload = upload.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise TransferError("That file is too large.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise TransferError("That file is not an Asset Tracking export.") from exc

    with archive:
        _validate_archive(archive)
        try:
            rows = json.loads(archive.read("assets.json"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise TransferError("That file is not an Asset Tracking export.") from exc
        if not isinstance(rows, list):
            raise TransferError("That file is not an Asset Tracking export.")

        added = 0
        skipped = 0
        for row in rows:
            if not isinstance(row, dict) or _is_duplicate(row):
                skipped += 1
                continue
            if _import_row(archive, row):
                added += 1
            else:
                skipped += 1
    return ImportResult(added=added, skipped=skipped)


def _asset_payload(asset: Asset) -> dict:
    return {
        "uuid": str(asset.uuid),
        "asset_number": asset.asset_number,
        "barcode_value": asset.barcode_value,
        "barcode_type": asset.barcode_type,
        "product_name": asset.product_name,
        "device_name": asset.device_name,
        "serial_number": asset.serial_number,
        "mac_address": asset.mac_address,
        "mac_address_2": asset.mac_address_2,
        "model_number": asset.model_number,
        "site_name": asset.site_name,
        "location": asset.location,
        "comments": asset.comments,
        "photo": asset.photo.name if asset.photo else "",
        "is_archived": asset.is_archived,
        "archived_at": _iso(asset.archived_at),
        "created_at": _iso(asset.created_at),
        "updated_at": _iso(asset.updated_at),
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _validate_archive(archive: zipfile.ZipFile) -> None:
    total = 0
    for info in archive.infolist():
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise TransferError("That file is too large.")
        if info.filename.startswith("/") or ".." in Path(info.filename).parts:
            raise TransferError("That file is not an Asset Tracking export.")
    try:
        manifest = json.loads(archive.read("manifest.json"))
    except (KeyError, json.JSONDecodeError) as exc:
        raise TransferError("That file is not an Asset Tracking export.") from exc
    if manifest.get("kind") != EXPORT_KIND or manifest.get("version") != EXPORT_VERSION:
        raise TransferError("That file is not an Asset Tracking export.")


def _is_duplicate(row: dict) -> bool:
    barcode = (row.get("barcode_value") or "").strip()
    asset_uuid = (row.get("uuid") or "").strip()
    if not barcode:
        return True
    if Asset.objects.filter(barcode_value=barcode).exists():
        return True
    if asset_uuid and Asset.objects.filter(uuid=asset_uuid).exists():
        return True
    if row.get("is_archived"):
        return False
    serial = (row.get("serial_number") or "").strip()
    if serial and Asset.objects.filter(is_archived=False, serial_number__iexact=serial).exists():
        return True
    macs = []
    for field_name in ("mac_address", "mac_address_2"):
        raw = (row.get(field_name) or "").strip()
        if not raw:
            continue
        try:
            macs.append(normalize_mac(raw))
        except ValueError:
            macs.append(raw)
    if not macs:
        return False
    return (
        Asset.objects.filter(is_archived=False)
        .filter(Q(mac_address__in=macs) | Q(mac_address_2__in=macs))
        .exists()
    )


def _import_row(archive: zipfile.ZipFile, row: dict) -> bool:
    number = row.get("asset_number")
    if not isinstance(number, int) or Asset.objects.filter(asset_number=number).exists():
        number = None
    photo_name = _extract_photo(archive, row.get("photo") or "")
    fields = dict(
        asset_number=number,
        barcode_value=(row.get("barcode_value") or "").strip(),
        barcode_type=row.get("barcode_type") or Asset.BarcodeType.QR,
        product_name=row.get("product_name") or "",
        device_name=row.get("device_name") or "",
        serial_number=row.get("serial_number") or "",
        mac_address=row.get("mac_address") or "",
        mac_address_2=row.get("mac_address_2") or "",
        model_number=row.get("model_number") or "",
        site_name=row.get("site_name") or "",
        location=row.get("location") or "",
        comments=row.get("comments") or "",
        photo=photo_name,
        is_archived=bool(row.get("is_archived")),
        archived_at=_parse_dt(row.get("archived_at")),
    )
    if row.get("uuid"):
        fields["uuid"] = row["uuid"]
    asset = Asset(**fields)
    try:
        asset.full_clean(exclude=["created_by"])
        asset.save()
    except (ValidationError, ValueError):
        return False
    created_at = _parse_dt(row.get("created_at"))
    updated_at = _parse_dt(row.get("updated_at"))
    updates = {}
    if created_at is not None:
        updates["created_at"] = created_at
    if updated_at is not None:
        updates["updated_at"] = updated_at
    if updates:
        Asset.objects.filter(pk=asset.pk).update(**updates)
    return True


def _extract_photo(archive: zipfile.ZipFile, photo_name: str) -> str:
    photo_name = photo_name.replace("\\", "/").lstrip("/")
    if not photo_name:
        return ""
    relative = Path(photo_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise TransferError("That file is not an Asset Tracking export.")
    if relative.parts[:2] != ("assets", "photos"):
        raise TransferError("That file is not an Asset Tracking export.")
    arcname = f"media/{photo_name}"
    names = set(archive.namelist())
    if arcname not in names:
        return ""
    target = (Path(settings.MEDIA_ROOT) / relative).resolve()
    root = Path(settings.MEDIA_ROOT).resolve()
    if root != target and root not in target.parents:
        raise TransferError("That file is not an Asset Tracking export.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(arcname) as source, target.open("wb") as dest:
        shutil.copyfileobj(source, dest)
    return photo_name


def _parse_dt(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    return parsed
