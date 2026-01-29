---
name: patent-filing-qc
description: Comprehensive quality control for U.S. patent application filing documents. Use when the user asks to QC, check, validate, or review patent filing documents before submission to the USPTO. Performs 70+ automated and manual checks across specification, drawings, ADS, declaration, assignment, and power of attorney documents. Detects cross-document inconsistencies, formatting issues, missing required fields, and common errors.
---

# Patent Filing QC

## Overview

This skill provides comprehensive quality control for U.S. patent application filing documents immediately before filing with the USPTO. It systematically checks for internal document errors, cross-document inconsistencies, USPTO compliance issues, and common filing mistakes across all required and optional filing documents.

## When to Use This Skill

Trigger this skill when the user requests any of the following:
- "QC this patent application"
- "Check these filing documents"
- "Validate this patent package"
- "Review this application before filing"
- Any request to quality check, validate, or review patent filing documents

## Workflow

### Step 1: Identify the Documents Folder

Confirm the folder path containing all filing documents. The folder should typically contain:
- Specification PDF (required)
- Drawings PDF (required)
- Application Data Sheet / ADS (required)
- Declaration (required)
- Assignment (optional but common)
- Power of Attorney (optional)

The documents may have various naming conventions. The QC script will automatically detect them based on common patterns.

### Step 2: Install Dependencies

Before running QC for the first time, ensure required dependencies are installed:

```bash
pip install PyPDF2 fpdf2 --break-system-packages
```

The `fpdf2` library is used for PDF report generation (pure Python, no system dependencies required).

### Step 3: Run the QC Script

Execute the comprehensive QC check:

```bash
python3 /path/to/skill/scripts/qc_patent_filing.py <folder-path>
```

Optional: Specify output directory for reports:
```bash
python3 /path/to/skill/scripts/qc_patent_filing.py <folder-path> --output-dir <output-path>
```

The script will:
1. Automatically detect all filing documents in the folder
2. Extract text from PDFs
3. Run all 70 quality control checks
4. Generate both Markdown and PDF report files in the documents folder

### Step 4: Ensure Both Reports Are Generated

The skill must generate two report files in the documents folder:
- `Patent_Filing_QC_Report.md` - Markdown format for easy reading
- `Patent_Filing_QC_Report.pdf` - PDF format for distribution/archiving

Both formats are **required**. The PDF is generated from the Markdown using `fpdf2`. If the automated script does not produce the PDF, generate it separately after writing the Markdown report.

### Step 5: Output Behavior

**IMPORTANT: Do NOT display the report content in the conversation.** The report files speak for themselves. After generation:
1. Confirm to the user that the reports have been generated
2. Provide the file paths for both `.md` and `.pdf` reports
3. Mention only the high-level summary counts (e.g., "3 Critical, 6 Warnings, 36 Passes")
4. Do NOT echo, paste, or reproduce the report content in the chat

Reports include:
- **Executive Summary** - Pass/Warning/Critical counts
- **Documents Found** - Which required/optional documents were detected
- **Critical Issues** - Must fix before filing (highlighted first)
- **Warnings** - Should review (may indicate problems)
- **Potential Issues (Low Confidence)** - Possible problems that could not be confirmed with certainty; requires manual verification
- **Detailed Results** - All 70 checks organized by category

### Step 6: Avoiding False Positives

Be careful to avoid these known sources of false positives:

1. **PDF text extraction spacing**: PDF text extraction can merge words together across line breaks or column boundaries (e.g., extracting "testsfor" when the actual document reads "tests for"). Before flagging a missing-space typo, re-examine the extracted text in context. If the supposed typo falls at a line break, column boundary, or page margin, it is likely an extraction artifact, not a real error. Do NOT flag spacing issues unless you are confident the error exists in the actual document.

2. **Patent drafting conventions for sentence structure**: In patent specifications, sentences may begin with subordinate conjunctions like "Although" and contain a complete dependent clause that ends with a period, without an explicit independent/main clause in the same sentence (e.g., "Although FIG. 3 illustrates a set that includes agent A, agent B, and agent C. Other agents can be introduced..."). This is an accepted patent drafting convention. Do NOT flag these as sentence fragments or suggest changing the period to a comma. Patent prose intentionally uses this construction.

3. **Customer numbers in ADS form fields**: When reading customer numbers from ADS screenshots or images, be aware that form field boundaries can visually clip leading digits. A 6-digit number like "150740" may appear to show only "50740" if the leading "1" is at the very edge of the field. Do NOT flag a customer number as incorrect based solely on visual appearance in a tight form field. Cross-reference with other documents (Declaration, POA) to confirm the correct number, and only flag a discrepancy if the number is clearly and unambiguously different.

4. **When confidence is low**: If a potential issue is detected but you cannot confirm it with high confidence (e.g., a possible misread from a screenshot, an ambiguous formatting pattern, or an extraction artifact that might also be a real error), do NOT include it as a Critical or Warning. Instead, include it in a separate **"Potential Issues (Low Confidence)"** section of the report. This section should clearly state what was observed, why confidence is low, and what the user should manually verify. This ensures nothing is silently ignored while keeping the Critical/Warning sections reliable.

### Step 7: Address Issues

If the user asks for help with specific issues found in the report:
1. **Fix critical issues first** - These must be corrected before filing
2. **Review warnings** - These may indicate problems or may be false positives
3. **Complete manual reviews** - Some checks require human verification
4. **Re-run QC after fixes** - Ensure all issues are resolved

## QC Check Categories

The skill performs 70 quality control checks across these categories:

### Cross-Document Consistency (8 checks)
- Inventor names match across ADS, declaration, assignment, and drawings
- Application title consistency
- Attorney docket number consistency
- Correspondence address alignment
- Assignee name consistency
- Filing date logic
- Inventor count matching
- Citizenship/residency information

### Document Completeness (4 checks)
- All required documents present
- ADS required fields complete
- Declaration signatures present
- Assignment signatures present (if included)

### Specification-Specific (15 checks)
- Sequential claim numbering
- Valid claim dependencies
- Figure references match drawings
- Reference numeral consistency
- Abstract present and length compliant (≤150 words)
- Required sections present (Background, Brief Description, Detailed Description, Claims)

### Drawings-Specific (5 checks)
- Sequential figure numbering
- Figure labels present
- Sheet numbering format
- Black and white compliance
- Legibility

### ADS-Specific (5 checks)
- Complete inventor addresses
- First named inventor identified
- Entity status specified
- Correspondence address complete
- Attorney/agent registration numbers

### Declaration-Specific (4 checks)
- All inventors named
- Proper oath vs. declaration format
- References correct application
- Logical execution date

### Assignment-Specific (5 checks)
- All assignors identified
- Assignee clearly named
- References correct application/docket
- Logical execution date
- Proper rights transfer language

### Power of Attorney-Specific (4 checks)
- All practitioners listed
- Registration numbers included
- Address matches ADS
- Proper signatures

### USPTO Formatting Compliance (5 checks)
- Line numbering every 5 lines
- Margin compliance (top: 2cm, left: 2.5cm, right: 2cm, bottom: 2cm)
- Font size (≥12 pt)
- Double spacing
- Page numbering

### Common Error Detection (5 checks)
- No placeholder text ([INSERT], TODO, XXX, etc.)
- No visible track changes or comments
- Consistent claim terminology
- Proper antecedent basis
- Claim terms defined in specification

### File Quality (4 checks)
- PDFs are text-searchable (not scanned images)
- Logical file naming
- No password protection
- Reasonable file sizes

### Cross-Reference Validation (4 checks)
- Claims reference specification elements
- Summary matches claims scope
- Figure count consistency
- Claim count verification

### Priority/Related Applications (3 checks)
- Priority claim consistency across documents
- Related application references match
- Foreign priority documentation

### Final Quality (5 checks)
- No obvious typos in critical fields
- Dates properly formatted
- No excessively long claims
- Specification supports all claims
- Consistent figure reference format

## Understanding Check Results

Each check produces one of five severity levels:

- **✅ PASS** - Check passed, no action needed
- **⚠️ WARNING** - Potential issue detected, review recommended
- **🚨 CRITICAL** - Issue must be fixed before filing
- **❓ LOW CONFIDENCE** - Possible issue detected but could not be confirmed with certainty; manual verification needed
- **ℹ️ INFO** - Manual review recommended, automated check not possible

## Best Practices

1. **Run QC multiple times** - After each round of fixes, re-run to ensure no new issues
2. **Don't ignore INFO items** - These require manual verification
3. **Fix critical issues immediately** - These will cause filing rejections
4. **Investigate warnings** - They may be false positives, but often indicate real problems
5. **Keep both reports** - Archive with filing records for future reference
6. **Review manually too** - Automated checks catch most issues, but human review is still essential

## Limitations

This skill provides automated detection for many issues, but cannot replace human judgment:

- Some checks require visual inspection (drawing legibility, formatting)
- Complex legal/technical issues need attorney review
- Context-dependent decisions (claim scope, specification adequacy) need human analysis
- The tool helps catch errors, but final responsibility rests with the practitioner

## Script Details

The main QC script is located at `scripts/qc_patent_filing.py` and includes:
- Automatic document detection using filename patterns
- PDF text extraction using PyPDF2
- Pattern matching for common issues
- Cross-document comparison logic
- Comprehensive reporting in Markdown and PDF formats

The script is designed to be run directly from Claude Code CLI without modification.
