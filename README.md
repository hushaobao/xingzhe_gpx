# 行者运动记录下载与 FIT 转换

两个独立脚本，支持命令行和 Python 函数调用。需要 Python 3.10 或更高版本。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

依赖统一由 `pyproject.toml` 管理。`requirements.txt` 保留历史内容，安装请使用上述命令；当前代码无需 `fake_useragent` 或 `tqdm`。

## 下载

登录行者网站，在浏览器开发者工具的网络请求中复制 Cookie，通过环境变量传入，无需修改源代码：

```powershell
$env:XINGZHE_COOKIE = "你的 Cookie"
python download_xingzhe_gpx.py
python download_xingzhe_gpx.py --year 2025 --month 10 --limit 100 --output results/gpx
```

Bash 中使用 `export XINGZHE_COOKIE='你的 Cookie'`。请勿将 Cookie 提交到版本库。

- 默认输出 `results/gpx`；列表响应保存在该目录的 `sport_records.json`。
- `--limit` 默认 10000，代表单次列表请求的上限，不保证服务端返回全部历史记录；可按年月分别下载。
- `--sport` 接受行者网站的运动类型编号；留空不筛选。
- 请求超时默认 30 秒，下载间隔默认 0.5 秒，可用 `--timeout`、`--delay` 调整。
- 默认跳过已有文件；`--overwrite` 强制重新下载。响应经过 GPX XML 校验后写入，单条失败继续处理其余记录。

## GPX 转 FIT

```powershell
python gpx2fit.py
python gpx2fit.py results/gpx/example.gpx --output results/fit
python gpx2fit.py results/gpx --workers 4 --sport cycling --overwrite
```

默认读取 `results/gpx` 中的 GPX 文件（不递归），输出到 `results/fit`，串行执行。`--workers` 可开启多进程；`--sport` 支持 `cycling`（默认）、`running` 和 `walking`。

每个文件生成一个活动、一个 session，每个非空轨迹段生成一圈。距离按段内相邻坐标计算，不连接分段间的空隙；总经过时间包含段间间隔，计时时长只累计段内时间，不额外推断运动/静止状态。结束时间使用最后一个轨迹点。保留坐标、时间、距离和可选海拔，不转换心率/踏频等扩展字段。

轨迹点必须有时间且整体不倒序；无时区时间按 UTC 处理。空轨迹段忽略，完全无轨迹点或缺少时间的文件报告失败。运动类型由参数指定，不从 GPX 自动识别。不再写入虚构的 Garmin 设备信息。

默认跳过已有 FIT；`--overwrite` 可重新转换。使用临时文件完成写入后再替换目标文件，避免失败时留下不完整结果。任意文件失败时退出码为 1，全部成功或跳过为 0；参数错误为 2。

安装后也可使用 `xingzhe-download` 和 `gpx-to-fit` 命令。原有函数 `run`、`gpx_to_fit`、`read_gpx_file` 和 `single_convert` 保留。

## 开发与验证

```powershell
python -m unittest discover -s tests -v
```

测试使用临时目录、生成的 GPX 和模拟 HTTP 响应，不需要真实 Cookie，也不会修改已有运动数据。转换逻辑参考原项目：https://github.com/rrym/gpx2fit/tree/master 。
