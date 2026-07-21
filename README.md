# PathCraft

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
