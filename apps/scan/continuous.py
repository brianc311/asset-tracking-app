import json

from django.db.models import Q

from apps.assets.mac import normalize_mac
from apps.assets.models import Asset

MODE_MAC = "mac"
MODE_SERIAL = "serial"
MODE_PAIR = "pair"
MAX_ROWS = 300


class ContinuousScanError(Exception):
    pass


def normalize_continuous_mode(raw) -> str:
    value = (raw or "").strip().lower()
    if value in (MODE_MAC, MODE_SERIAL, MODE_PAIR):
        return value
    return MODE_MAC


def parse_continuous_rows(raw) -> list[dict]:
    try:
        rows = json.loads(raw or "")
    except json.JSONDecodeError as exc:
        raise ContinuousScanError("The scan list could not be read. Scan again.") from exc
    if not isinstance(rows, list):
        raise ContinuousScanError("The scan list could not be read. Scan again.")
    if not rows:
        raise ContinuousScanError("Scan at least one code before finishing.")
    if len(rows) > MAX_ROWS:
        raise ContinuousScanError(f"Scan at most {MAX_ROWS} codes at a time.")
    return [row if isinstance(row, dict) else {} for row in rows]


def shared_mac_value(raw) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    try:
        return normalize_mac(value)
    except ValueError as exc:
        raise ContinuousScanError(str(exc)) from exc


def prepare_rows(mode, raw_rows, shared_serial="", shared_mac="") -> tuple[list[dict], list[str]]:
    serial_for_all = (shared_serial or "").strip()
    mac_for_all = shared_mac_value(shared_mac) if mode == MODE_SERIAL else ""
    problems = []
    prepared = []
    for index, raw in enumerate(raw_rows, start=1):
        serial = (raw.get("serial") or "").strip()
        mac_raw = (raw.get("mac") or "").strip()
        if mode == MODE_MAC:
            mac_raw = mac_raw or serial
            serial = serial_for_all
        elif mode == MODE_SERIAL:
            serial = serial or mac_raw
            mac_raw = mac_for_all
        mac = ""
        if mac_raw:
            try:
                mac = normalize_mac(mac_raw)
            except ValueError:
                problems.append(f"Row {index}: {mac_raw} is not a valid MAC address.")
                continue
        if mode == MODE_MAC and not mac:
            problems.append(f"Row {index}: no MAC address was scanned.")
            continue
        if mode == MODE_SERIAL and not serial:
            problems.append(f"Row {index}: no serial number was scanned.")
            continue
        if mode == MODE_PAIR and not serial and not mac:
            problems.append(f"Row {index}: no serial number or MAC address was scanned.")
            continue
        prepared.append({"number": index, "serial": serial, "mac": mac})
    return prepared, problems


def split_duplicates(rows) -> tuple[list[dict], list[str]]:
    kept = []
    problems = []
    seen_serial = {}
    seen_mac = {}
    for row in rows:
        reasons = []
        serial = row["serial"]
        mac = row["mac"]
        if serial:
            key = serial.casefold()
            if key in seen_serial:
                reasons.append(f"serial {serial} duplicates row {seen_serial[key]}")
            else:
                existing = (
                    Asset.objects.filter(is_archived=False, serial_number__iexact=serial)
                    .order_by("asset_number")
                    .first()
                )
                if existing:
                    reasons.append(f"serial {serial} is already on asset #{existing.asset_number}")
        if mac:
            if mac in seen_mac:
                reasons.append(f"MAC {mac} duplicates row {seen_mac[mac]}")
            else:
                existing = (
                    Asset.objects.filter(is_archived=False)
                    .filter(Q(mac_address=mac) | Q(mac_address_2=mac))
                    .order_by("asset_number")
                    .first()
                )
                if existing:
                    reasons.append(f"MAC {mac} is already on asset #{existing.asset_number}")
        if reasons:
            problems.append(f"Row {row['number']}: " + "; ".join(reasons) + ".")
            continue
        if serial:
            seen_serial[serial.casefold()] = row["number"]
        if mac:
            seen_mac[mac] = row["number"]
        kept.append(row)
    return kept, problems
