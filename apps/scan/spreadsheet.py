import csv
import io
import zipfile
from xml.sax.saxutils import escape

EXPORT_COLUMNS = (
    "Row",
    "Asset number",
    "Site",
    "Product",
    "Device name",
    "Serial",
    "MAC",
    "MAC 2",
    "Model",
    "Location",
    "Comment",
)


def continuous_export_rows(assets) -> list[list[str]]:
    rows = [list(EXPORT_COLUMNS)]
    for index, asset in enumerate(assets, start=1):
        rows.append(
            [
                str(index),
                "" if asset.asset_number is None else str(asset.asset_number),
                asset.site_name or "",
                asset.product_name or "",
                asset.device_name or "",
                asset.serial_number or "",
                asset.mac_address or "",
                asset.mac_address_2 or "",
                asset.model_number or "",
                asset.location or "",
                asset.comments or "",
            ]
        )
    return rows


def render_csv(rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def render_xlsx(rows) -> bytes:
    sheet = _worksheet_xml(rows)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _package_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _cell_xml(column: int, row_number: int, value: str) -> str:
    text = escape(_excel_text(value))
    ref = f"{_column_name(column)}{row_number}"
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def _excel_text(value: str) -> str:
    return "".join(ch for ch in str(value) if ch >= " " or ch in "\t")


def _worksheet_xml(rows) -> str:
    body = []
    for row_number, row in enumerate(rows, start=1):
        cells = "".join(_cell_xml(column, row_number, value) for column, value in enumerate(row, start=1))
        body.append(f'<row r="{row_number}">{cells}</row>')
    sheet_rows = "".join(body)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{sheet_rows}</sheetData>"
        "</worksheet>"
    )


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )


def _package_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="Continuous scan" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )


def _workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
