# PathCraft

PathCraft 是仅支持 Windows 10/11 的便携桌面文件处理 App，提供：

- 批量添加前缀或后缀
- 批量删除或替换文件名内容
- 使用 Excel、CSV 或 TXT 映射表重命名
- 识别电子发票购买方并将 PDF 转换为 PNG
- 执行前完整预览、冲突阻止和失败回滚
- 后台执行操作，完成后自动刷新当前目录的文件列表

## 直接使用

获取 [PathCraft.exe](dist/PathCraft.exe) 后双击即可运行。

不需要安装，不需要管理员权限，也不需要单独安装 Python、`uv` 或依赖包。EXE 可以复制到
任意普通目录或 U 盘中运行。PathCraft 不提供 CLI、安装脚本或 Linux 版本。

首次启动单文件 EXE 时，Windows 需要将内置运行文件解压到临时目录，因此可能比后续窗口
操作稍慢。如果 Windows SmartScreen 显示未知发布者，这是因为当前 EXE 尚未进行代码签名。

## 使用流程

选择工作目录和需要执行的操作，生成预览后点击“执行”即可开始处理，不需要再次确认。
处理完成后不会弹出结果窗口；预览内容会自动清空，文件列表会刷新为当前工作目录的实际内容，
成功、跳过和失败数量会显示在窗口底部的状态栏中。

## 从源码构建便携 EXE

开发者需要先安装 `uv`，然后在 PowerShell 中运行：

```powershell
.\build.ps1
```

脚本会在隔离的构建环境中使用 PyInstaller，最终只需分发：

```text
dist\PathCraft.exe
```

构建脚本仅打包 App 实际使用的模块，并排除数据分析、绘图和终端界面等可选依赖。
`build/` 中的内容都是临时构建文件，不需要分发。

## 开发与测试

```powershell
uv sync
uv run python -m unittest discover -v
```

开发环境中可以执行 `uv run pathcraft` 启动 GUI；最终用户只使用便携 EXE。
项目不包含 GitHub Actions 或其他 GitHub CI 配置，测试与构建均在本地执行。
