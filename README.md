# PathCraft

PathCraft 是仅支持 Windows 10/11 的便携桌面文件处理 App，提供：

- 批量添加前缀或后缀
- 批量删除或替换文件名内容
- 使用 Excel、CSV 或 TXT 映射表重命名
- 识别电子发票购买方并将 PDF 转换为 PNG
- 执行前完整预览、冲突阻止和失败回滚
- 后台执行操作，完成后自动刷新当前目录的文件列表


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
