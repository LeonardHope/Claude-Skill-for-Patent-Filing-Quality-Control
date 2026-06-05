"""Generate a tiny sample declaration PDF for the Phase-0 spike.

Throwaway: just enough real text, on two pages, to prove that we can locate a
phrase (an inventor surname) and get its page + bounding box. Coordinates are
in points (unit="pt") so they line up directly with pdfplumber's output.

Run:  python3 app/sample/make_sample.py
"""
from pathlib import Path
from fpdf import FPDF

OUT = Path(__file__).resolve().parent / "Declaration.pdf"


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


if __name__ == "__main__":
    build()
