"""Minimal .xlsx writer using only the standard library.

The notebook container has no openpyxl/xlsxwriter, and we do not install
packages on the shared server, so this writes the Office Open XML parts
directly: one sheet per table, bold frozen header row, autofilter, column widths.
"""

import re
import zipfile
from xml.sax.saxutils import escape

ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
MAX_CELL = 32767


def _col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref, value, style):
    if isinstance(value, bool):
        value = str(value).upper()
    if isinstance(value, (int, float)) and value == value:  # not NaN
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    text = ILLEGAL.sub("", "" if value is None else str(value))[:MAX_CELL]
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def _sheet_xml(header, rows, widths):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
           'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>']
    for i, w in enumerate(widths, start=1):
        out.append(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>')
    out.append("</cols><sheetData>")
    out.append('<row r="1">' + "".join(_cell(f"{_col(i)}1", h, 1) for i, h in enumerate(header, 1)) + "</row>")
    for r, row in enumerate(rows, start=2):
        out.append(f'<row r="{r}">' + "".join(_cell(f"{_col(i)}{r}", v, 2) for i, v in enumerate(row, 1)) + "</row>")
    last = f"{_col(len(header))}{len(rows) + 1}"
    out.append(f'</sheetData><autoFilter ref="A1:{last}"/></worksheet>')
    return "".join(out)


def write_xlsx(path, sheets):
    """sheets: list of (name, header list, rows list-of-lists, widths list or None)."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        names = []
        for i, (name, header, rows, widths) in enumerate(sheets, start=1):
            name = re.sub(r"[\[\]:*?/\\]", "_", name)[:31]
            names.append(name)
            widths = widths or [min(max(len(str(h)) + 4, 12), 60) for h in header]
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(header, rows, widths))
        n = len(names)
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, n + 1))
                   + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   "</Relationships>")
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(nm)}" sheetId="{i}" r:id="rId{i}"/>' for i, nm in enumerate(names, 1))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, n + 1))
                   + f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   "</Relationships>")
        z.writestr("xl/styles.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
                   '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
                   '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
                   '<fill><patternFill patternType="solid"><fgColor rgb="FF0B2D26"/></patternFill></fill></fills>'
                   '<borders count="1"><border/></borders>'
                   '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
                   '<cellXfs count="3"><xf/>'
                   '<xf fontId="1" fillId="2" applyFont="1" applyFill="1"/>'
                   '<xf applyAlignment="1"><alignment vertical="top"/></xf></cellXfs>'
                   "</styleSheet>")
