# PathCraft 项目结构优化完成度

更新时间：2026-07-20

## 1. 当前结论

本轮优化已完成测试拆分、CLI 与交互层拆分、包级入口补齐、PDF 职责拆分、PDF 输出归档流程、共享异常与配置整理及相关回归修复。项目采用 `src/` 源码布局，并通过 uv 进行 editable 安装。

当前阶段状态：

| 阶段 | 状态 | 说明 |
|---|---|---|
| 阶段一：测试对齐 | 已完成 | 原单体测试已按领域拆分，原有测试无遗漏 |
| 阶段二：源码布局与入口 | 已完成 | 使用 `src/pathcraft/` 与 uv editable 安装，支持包级入口 |
| 阶段三：职责拆分 | 已完成 | CLI、交互、PDF 识别/渲染及跨模块异常与配置已拆分 |
| 阶段四：PDF 输出归档 | 已完成 | PNG 写入源目录，成功 PDF 移入同目录 `.pdf/` |

此前的 CLI 与测试拆分已提交为 `0732f28`；当前 `src/` 迁移、领域异常、集中配置和 CI 工作仍在工作区中，尚未提交。

## 2. 当前项目结构

```text
PathCraft/
├── .github/
│   └── workflows/
│       └── tests.yml
├── src/
│   └── pathcraft/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── exceptions.py
│       ├── main.py
│       ├── mapping_rename.py
│       ├── pdf/
│       │   ├── __init__.py
│       │   ├── extract.py
│       │   └── render.py
│       ├── pdf_convert.py
│       ├── prompts.py
│       ├── rename.py
│       ├── rules.py
│       ├── scanner.py
│       └── utils.py
├── tests/
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_entrypoints.py
│   ├── test_exceptions.py
│   ├── test_mapping_rename.py
│   ├── test_pdf_convert.py
│   ├── test_pdf_extract.py
│   ├── test_pdf_render.py
│   ├── test_rename.py
│   ├── test_rules.py
│   ├── test_scanner.py
│   └── test_utils.py
├── main.py
├── pyproject.toml
└── README.md
```

## 3. 已完成事项

### 3.1 测试拆分

- 删除原单体 `tests/test_pathcraft.py`。
- 将测试拆分到 CLI、Prompts、Rename、Rules、Scanner、Utils 等领域文件。
- 原有 32 个测试无遗漏。
- 当前共有 63 个测试。
- 新增入口测试，覆盖包入口和旧模块兼容入口。

### 3.2 CLI 与交互层拆分

- 原 `src/pathcraft/main.py` 的实现已迁移至 `src/pathcraft/cli.py` 和 `src/pathcraft/prompts.py`。
- `cli.py` 负责配置、重命名预览、调度和执行流程。
- `prompts.py` 负责目录与文件选择、菜单和重命名确认。
- `src/pathcraft/main.py` 保留为旧模块路径兼容层。
- 拆分前后的所有原函数已做 AST 对比，没有函数遗漏、重复或实现变化。

### 3.3 入口整理

- 根目录 `main.py` 转发到 `pathcraft.cli.main`。
- 新增 `src/pathcraft/__main__.py`，支持 `python -m pathcraft`。
- 恢复 `python -m pathcraft.main` 的旧入口兼容行为。
- 所有入口均使用 `raise SystemExit(main())` 保留退出状态码。

### 3.4 已修复问题

- 修复缺少 `pathcraft.__main__` 导致包级 `-m` 入口不可用的问题。
- 修复拆分后 `python -m pathcraft.main` 静默退出的兼容回归。
- 修复 `scanner.is_hidden` 在 `stat_result` 没有 `st_flags` 时抛出异常的问题。
- 更新 README 中已经过期的项目结构。
- 修正 README 中多页 PNG 命名与实际实现不一致的问题。
- 修复 Windows CI 使用 CP1252 代码页时中文输出失败和入口子进程断言失真的问题。

### 3.5 PDF 职责拆分

- 新增 `src/pathcraft/pdf/extract.py`，负责 PDF 扫描、购买方识别和输出路径规划。
- 新增 `src/pathcraft/pdf/render.py`，负责事务式 PNG 渲染、多文件执行和进度回调。
- `src/pathcraft/pdf_convert.py` 保留为旧导入路径兼容层，内部 CLI 已改用新的 `pathcraft.pdf` API。
- PDF 测试已拆成识别规划、渲染执行和兼容导出三个部分。
- 新增购买方名称清洗、加密/空 PDF 隔离、非法 DPI 和预览后页数变化边界测试。
- 新增归档重名规避和归档失败回滚测试。

### 3.6 PDF 输出与归档流程

- PNG 直接生成在源 PDF 所在目录，不再创建 `png/` 子目录。
- 每个源目录按需创建 `.pdf/` 隐藏目录，成功转换的 PDF 在所有页面提交后移入该目录。
- `.pdf/` 属于隐藏目录，后续扫描不会再次处理其中已经归档的 PDF。
- 图片重名时自动追加 `_2`、`_3`；归档 PDF 重名时使用相同策略，均不覆盖已有文件。
- 渲染、图片提交或 PDF 归档任一步失败时，清理由本次转换生成的 PNG，并将源 PDF 保留在原位置。
- PDF 转换期间只刷新当前文件和页面进度，不再逐条打印完成文件列表。
- PDF 转换完成汇总使用彩色单行文本显示：成功为亮绿色，存在失败时为亮黄色。

### 3.7 共享异常与配置整理

- `src/pathcraft/exceptions.py` 统一应用、PDF、内容、加密、空文档、购买方识别、页数变化、渲染和依赖错误的异常层次。
- 保留 `pathcraft.utils.UserCancelled` 与 `pathcraft.pdf.PdfDependencyError` 的兼容导入，不破坏原有调用。
- `src/pathcraft/config.py` 集中默认/最低 PDF DPI、图片扩展名、映射扩展名和重命名进度阈值。
- PDF 转换不再询问 DPI 或显示转换预览；选择目录后直接使用 `DEFAULT_PDF_DPI` 执行并显示进度。
- 目录范围选择步骤已移除；所有功能默认递归处理所选目录及其非隐藏子目录。
- `_ReturnToMainMenu`、`_DirectorySelectionUnavailable` 等模块内部控制异常继续保留在各自模块。
- 原模块继续兼容导出扩展名常量，避免破坏已有导入。

### 3.8 严格警告与跨平台 CI

- `load_pymupdf()` 在依赖导入边界精确过滤 PyMuPDF/SWIG 的三条已知弃用警告，不屏蔽项目或其他依赖的警告。
- 修复 PyMuPDF 1.28.0 在 macOS 上配合 `python -W error` 导入时触发原生退出码 139 的问题。
- 新增 GitHub Actions 工作流，覆盖 Windows、macOS、Linux，以及 Python 3.10、3.12、3.14。
- CI 执行锁定安装、严格警告测试、编译检查、依赖检查和发行包构建。
- CLI 启动时将可配置的标准输出和错误流切换为 UTF-8，CI 同时启用 Python UTF-8 模式。
- Windows 与 macOS 的目录选择器、映射文件选择器和取消流程已完成人工冒烟测试。
- 主功能菜单采用无边框 ASCII 标识、`➤` 当前项和底部快捷键提示的紧凑布局。

## 4. 架构决定

### 4.1 使用 editable 安装

项目采用标准 `src/` 布局，由 uv 以 editable 模式关联源码：

- 源码包位于 `src/pathcraft/`；
- `[tool.uv] package = true`；
- 使用 `uv sync` 创建 editable 安装；
- 推荐使用 `uv run python -m pathcraft` 运行；
- 修改源码后无需重新构建或安装。

根目录 `main.py` 继续作为兼容入口保留。

## 5. 已执行验证

本轮已完成以下验证：

```shell
uv sync --reinstall
uv run python -W error -m unittest discover -q
uv run python -m compileall -q main.py src/pathcraft tests
uv pip check
git diff --check
uv build
```

验证结果：

- 依赖重装成功；
- 63 项测试在警告视为错误的模式下全部通过；
- 使用 `PYTHONIOENCODING=cp1252` 模拟 Windows 旧代码页时，测试仍全部通过；
- editable 安装在仓库外导入时仍指向 `src/pathcraft/`；
- Python 编译检查通过；
- 已安装依赖兼容性检查通过；
- source distribution 和 wheel 构建成功；
- wheel 包含 `src/pathcraft/__main__.py`、`src/pathcraft/cli.py`、`src/pathcraft/prompts.py` 和 `src/pathcraft/pdf/` 对应的包文件；
- 在隔离环境安装 wheel 后，`python -m pathcraft` 和 `python -m pathcraft.main` 均能到达 CLI 入口；
- 使用 `/home/ubuntu/data` 中的 28 份电子发票完成真实转换验证：生成 28 张 PNG，并将 28 份源 PDF 归档到 `.pdf/`；
- 真实验证中未创建 `png/` 子目录，生成文件数量与规划数量一致；
- Git 差异格式检查通过。

## 6. 当前已知限制

- 本次 editable 安装验证环境为 macOS；此前 28 份真实发票转换验证环境为 Linux。
- PyMuPDF/SWIG 的严格警告兼容处理是针对已确认的三条导入警告；升级 PyMuPDF 后应重新验证过滤规则是否仍有必要。
- GitHub Actions 工作流已通过本地 YAML 解析，但需要推送到 GitHub 后完成首次远程矩阵运行。
- 当前工作区存在未提交变更，继续工作前不要覆盖或回退这些文件。

## 7. 下次继续顺序

建议从以下顺序继续：

1. 提交并推送当前变更，观察 GitHub Actions 首次跨平台矩阵运行。
2. 根据真实使用反馈继续进行小范围职责优化或缺陷修复。

每个小阶段结束后至少执行：

```shell
uv sync --reinstall
uv run python -W error -m unittest discover -v
uv run python -m pathcraft
git diff --check
```
