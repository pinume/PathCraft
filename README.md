# PathCraft

PathCraft is a secure, cross-platform file processing CLI that supports batch renaming files and converting e-invoice PDFs into PNGs named after the buyer.

## Features

### Batch Rename

- Add a fixed prefix or suffix
- Remove or replace specified content in filenames
- Batch rename based on an Excel, CSV, or TXT mapping table
- By default processes all non-hidden file types within the selected directory scope
- Recursively processes the selected directory and all non-hidden subdirectories, with conflict detection, two-phase renaming, failure rollback, and progress feedback for large batches

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
- Supports Windows and Linux
- Batch rename uses only the Python standard library
- PDF conversion uses PyMuPDF
- Excel mapping table reading uses openpyxl
- Terminal text width calculation uses wcwidth

## 安装与使用

PathCraft 是一个个人命令行工具。安装后可以在任意目录直接输入
`pathcraft` 启动，不需要进入项目目录。

### Ubuntu 安装

如果尚未安装 uv：

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

重新打开终端，然后获取并安装 PathCraft：

```shell
git clone https://github.com/pinume/PathCraft.git
cd PathCraft
./install.sh
```

如果提示没有执行权限：

```shell
chmod +x install.sh
./install.sh
```

安装完成后重新打开终端，然后运行：

```shell
pathcraft
```

### Windows 安装

在 PowerShell 中安装 uv：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

重新打开 PowerShell，然后获取并安装 PathCraft：

```powershell
git clone https://github.com/pinume/PathCraft.git
cd PathCraft
.\install.ps1
```

如果 PowerShell 阻止本地脚本运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

安装完成后重新打开 PowerShell，然后运行：

```powershell
pathcraft
```

### 安装后删除项目目录

安装脚本使用非 editable 模式，将 PathCraft 复制到 uv 的独立工具环境。
确认 `pathcraft` 可以正常启动后，可以删除克隆下来的 `PathCraft` 项目目录，
不会影响已经安装的命令。删除前请确认个人修改已经提交、推送或备份。

Ubuntu 可以查看工具及命令的实际安装位置：

```shell
uv tool list --show-paths
uv tool dir
uv tool dir --bin
command -v pathcraft
```

Windows PowerShell 可以执行：

```powershell
uv tool list --show-paths
uv tool dir
uv tool dir --bin
Get-Command pathcraft
```

### 更新

如果保留了项目目录，Ubuntu 执行：

```shell
cd PathCraft
git pull
./install.sh
```

Windows PowerShell 执行：

```powershell
cd PathCraft
git pull
.\install.ps1
```

如果已经删除项目目录，Windows 和 Ubuntu 都可以直接从 GitHub 更新：

```shell
uv tool install --reinstall "git+https://github.com/pinume/PathCraft.git"
```

### 卸载

Windows 和 Ubuntu 都可以执行：

```shell
uv tool uninstall pathcraft
```

## Batch Rename

Run the package entry point to enter interactive mode, where you can choose from four renaming methods or PDF to PNG conversion:

```shell
pathcraft
```

The interactive menu uses an unboxed ASCII header, a `➤` marker for the current
selection, and keyboard navigation with Up/Down, Enter, Q, and Esc.
Windows and Linux use the same text-editor state model in the workspace. Arrow
keys move the cursor, Home/End jump to either end, Backspace/Delete edit around
the cursor, and completed prompts scroll upward when the workspace is full.

### Rename via Mapping Table

After selecting "Batch rename via mapping table" from the interactive menu, choose an `.xlsx`, `.xlsm`, `.csv`, or `.txt` file. The program will display the detected column headers, and you'll select the original-name column and new-name column through the menu — no need to type column headers manually.
On Ubuntu, PathCraft uses the available system file picker and falls back to an
arrow-key terminal file picker when no graphical picker is available, so the file
path normally does not need to be typed manually. If manual entry is still
required, the path is edited inside the main workspace with cursor-key support;
validation errors remain above the next input line.
The selected mapping file, detected headers, and completed column choice remain in
the main workspace while the next choice appears below. When the workspace is
full, older completed lines and long column lists scroll while keeping the current
selection visible.

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
pathcraft
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

GitHub Actions runs the same checks on Windows and Linux. The workflow
also covers Python 3.10, 3.12, and 3.14, compiles the source tree, checks the
installed dependency set, and builds both distributions.

PDF batches continue after an individual file fails. To print the full traceback
for those isolated failures, enable diagnostic mode before starting PathCraft:

```shell
PATHCRAFT_DEBUG=1 pathcraft
```

In Windows PowerShell:

```powershell
$env:PATHCRAFT_DEBUG = "1"
pathcraft
```

Project structure:

```text
├── .github/
│   └── workflows/
│       └── tests.yml
├── install.ps1
├── install.sh
├── main.py
├── pyproject.toml
├── src/
│   └── pathcraft/
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── diagnostics.py
│       ├── dialogs.py
│       ├── exceptions.py
│       ├── filesystem.py
│       ├── mapping_rename.py
│       ├── main.py
│       ├── pdf/
│       │   ├── __init__.py
│       │   ├── extract.py
│       │   └── render.py
│       ├── pdf_convert.py
│       ├── prompts.py
│       ├── rename.py
│       ├── rules.py
│       ├── scanner.py
│       ├── terminal_editor.py
│       ├── terminal_layout.py
│       ├── terminal_menu.py
│       └── utils.py
└── tests/
    ├── test_cli.py
    ├── test_config.py
    ├── test_diagnostics.py
    ├── test_entrypoints.py
    ├── test_exceptions.py
    ├── test_mapping_rename.py
    ├── test_pdf_convert.py
    ├── test_pdf_extract.py
    ├── test_pdf_render.py
    ├── test_prompts.py
    ├── test_rename.py
    ├── test_rules.py
    ├── test_scanner.py
    └── test_utils.py
```

The `main.py` in the root directory is a compatibility entry point:

```shell
python main.py
```
