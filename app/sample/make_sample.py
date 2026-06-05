"""Generate tiny sample filing PDFs for the v2 viewer + evidence tests.

Just enough real text to prove we can locate phrases (inventor surnames, the
title, the docket) and get their page + bounding box. Title/docket use the
generic BASE_ADS values from the test suite (no client data). Coordinates are
in points (unit="pt") so they line up directly with pdfplumber's output.

Run:  python3 app/sample/make_sample.py
"""
from pathlib import Path
from fpdf import FPDF

HERE = Path(__file__).resolve().parent
OUT = HERE / "Declaration.pdf"
TITLE = "MEMORY-EFFICIENT INFERENCE FOR LARGE LANGUAGE MODELS"
DOCKET = "LUM-0142US"


def build():
    pdf = FPDF(unit="pt", format="letter")  # 612 x 792 pt
    pdf.set_auto_page_break(False)

    # ---- Page 1: inventor 1 ----
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.set_xy(72, 90)
    pdf.cell(0, 18, "DECLARATION (37 CFR 1.63)")
    pdf.set_font("Helvetica", size=11)
    pdf.set_xy(72, 130)
    pdf.cell(0, 14, "Attorney Docket Number: LUM-0142US")
    pdf.set_xy(72, 170)
    pdf.cell(0, 14, "I hereby declare that I am an original inventor of the claimed invention.")
    pdf.set_xy(72, 210)
    pdf.cell(0, 14, "Inventor 1")
    pdf.set_font("Helvetica", size=12)
    pdf.set_xy(72, 232)
    pdf.cell(0, 16, "Sarah J. CHEN")          # <-- locate target on page 1
    pdf.set_font("Helvetica", size=11)
    pdf.set_xy(72, 260)
    pdf.cell(0, 14, "/Sarah J. Chen/    Date: 2026-05-09")

    # ---- Page 2: inventor 2 ----
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.set_xy(72, 90)
    pdf.cell(0, 14, "I hereby declare that I am an original inventor of the claimed invention.")
    pdf.set_xy(72, 130)
    pdf.cell(0, 14, "Inventor 2")
    pdf.set_font("Helvetica", size=12)
    pdf.set_xy(72, 152)
    pdf.cell(0, 16, "Aditya Vikram MEHTA")    # <-- locate target on page 2
    pdf.set_font("Helvetica", size=11)
    pdf.set_xy(72, 180)
    pdf.cell(0, 14, "/Aditya Vikram Mehta/    Date: 2026-05-09")

    pdf.output(str(OUT))
    print(f"wrote {OUT}")


def build_spec():
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_font("Helvetica", size=13)
    pdf.set_xy(72, 90)
    pdf.cell(0, 18, TITLE)                       # title near the top (Check 2)
    pdf.set_font("Helvetica", size=11)
    pdf.set_xy(72, 140)
    pdf.cell(0, 14, "BACKGROUND")
    pdf.set_xy(72, 162)
    pdf.cell(0, 14, "Modern systems require efficient inference.")
    out = HERE / "Specification.pdf"
    pdf.output(str(out)); print(f"wrote {out}")


def build_drawings():
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.set_xy(72, 54)
    pdf.cell(0, 14, f"(Docket No.: {DOCKET})")   # margin docket label (Check 23)
    pdf.set_xy(420, 54)
    pdf.cell(0, 14, "Sheet 1 of 1")
    pdf.set_font("Helvetica", size=12)
    pdf.set_xy(260, 380)
    pdf.cell(0, 16, "FIG. 1")
    out = HERE / "Drawings.pdf"
    pdf.output(str(out)); print(f"wrote {out}")


if __name__ == "__main__":
    build()
    build_spec()
    build_drawings()
