# PathCraft

PathCraft is a secure, cross-platform file processing CLI that supports batch renaming files and converting e-invoice PDFs into PNGs named after the buyer.

## Features

### Batch Rename

- Add a fixed prefix or suffix
- Remove or replace specified content in filenames
- Batch rename based on an Excel, CSV, or TXT mapping table
- By default processes all non-hidden file types within the selected directory scope
- Recursively processes the selected directory and all non-hidden subdirectories, with preview, conflict detection, two-phase renaming, failure rollback, and progress feedback for large batches

### PDF to PNG

- Recursively scans the selected directory and all non-hidden subdirectories for e-invoice PDFs, with case-insensitive extension matching
- Identifies the buyer name from the "Name:" field of the buyer section on the first page, without using OCR
- Renders each page as a lossless RGB PNG using the DPI configured in `src/pathcraft/config.py`
- Automatically avoids overwriting images with the same name
- Writes PNG files directly beside the source PDF, without creating a `png` folder
- After a successful conversion, moves the source PDF into a `.pdf` hidden folder beside it
- Processes each PDF transactionally; if rendering or archiving fails, it removes images produced during that run and leaves the source PDF in place

## Requirements

- Python 3.10 or higher
- Supports Windows, macOS, and Linux
- Batch rename uses only the Python standard library
- PDF conversion uses PyMuPDF
- Excel mapping table reading uses openpyxl

## Installation

Using uv:

```shell
uv sync
uv run python -m pathcraft
```

The source package lives under `src/pathcraft/`. During `uv sync`, uv installs
it in editable mode, so `python -m pathcraft` always runs the current source and
source changes do not require rebuilding or reinstalling the project.

The project uses uv's copy install mode by default, which is compatible with cloud file directories that don't support hard links, such as Windows Desktop and OneDrive. If the virtual environment previously failed to sync in hard-link mode, run once:

```powershell
uv sync --reinstall
```

## Batch Rename

Run the package entry point to enter interactive mode, where you can choose from four renaming methods or PDF to PNG conversion:

```shell
uv run python -m pathcraft
```

The interactive menu uses an unboxed ASCII header, a `➤` marker for the current
selection, and keyboard navigation with Up/Down, Enter, Q, and Esc.

### Rename via Mapping Table

After selecting "Batch rename via mapping table" from the interactive menu, choose an `.xlsx`, `.xlsm`, `.csv`, or `.txt` file. The program will display the detected column headers, and you'll select the original-name column and new-name column through the menu — no need to type column headers manually.

Example mapping table:

```text
Current File,Renamed To
old_name.jpg,new_name.jpg
draft_contract,final_contract
```

If the original name includes an extension, matching is done against the full filename; if it doesn't, matching is done against the file's base name. If the new name has no extension, the original extension is preserved. When multiple files with the same name appear across recursive directories, they are flagged as conflicts and will not be processed.

## PDF to PNG

Launch the program directly and choose "PDF to PNG" from the interactive menu, then select the directory containing the PDFs:

```shell
uv run python -m pathcraft
```

The program recursively processes the selected directory and every non-hidden subdirectory, then starts conversion immediately without an additional preview or confirmation step. Recognition failures are reported directly. The render DPI is controlled only by `DEFAULT_PDF_DPI` in `src/pathcraft/config.py`, and conversion progress is shown at both the PDF-file level and the page level.

Output images are placed directly in the directory of the corresponding PDF:

- Single page: `BuyerName.png`
- Multiple pages: `BuyerName_第1页.png`, `BuyerName_第2页.png`
- Duplicate names: automatically appended with `_2`, `_3`, etc., without overwriting existing files

After all pages are written successfully, the source PDF is moved to `.pdf/OriginalName.pdf` in the same directory. Existing archived PDFs are not overwritten; `_2`, `_3`, and so on are appended when needed. The `.pdf` directory is hidden from PathCraft's scanner.

Encrypted PDFs, empty PDFs, scanned documents, or files where the buyer name cannot be identified will be reported as failures and retained in their original location. A failure on one file does not interrupt processing of others.

## Development and Testing

```shell
uv sync
uv run python -W error -m unittest discover -v
```

GitHub Actions runs the same checks on Windows, macOS, and Linux. The workflow
also covers Python 3.10, 3.12, and 3.14, compiles the source tree, checks the
installed dependency set, and builds both distributions.

Project structure:

```text
.github/
└── workflows/
    └── tests.yml
src/
└── pathcraft/
    ├── __main__.py
    ├── cli.py
    ├── config.py
    ├── exceptions.py
    ├── mapping_rename.py
    ├── main.py
    ├── pdf/
    │   ├── __init__.py
    │   ├── extract.py
    │   └── render.py
    ├── pdf_convert.py
    ├── prompts.py
    ├── rename.py
    ├── rules.py
    ├── scanner.py
    └── utils.py
tests/
├── test_cli.py
├── test_config.py
├── test_entrypoints.py
├── test_exceptions.py
├── test_mapping_rename.py
├── test_pdf_convert.py
├── test_pdf_extract.py
├── test_pdf_render.py
├── test_rename.py
├── test_rules.py
├── test_scanner.py
└── test_utils.py
```

The `main.py` in the root directory is a compatibility entry point:

```shell
python main.py
```
