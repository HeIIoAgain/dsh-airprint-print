# dsh-airprint-print

[English](README.en.md) | 简体中文

无 CUPS、无驱动、不需要 root，直接把页面渲染成 **Apple Raster（URF）**，再通过 IPP `Print-Job` 发给 AirPrint / Mopria 打印机。

实测针对一类很常见的便宜网络打印机：只开 IPP 631、`document-format-supported = application/octet-stream`、`document-format-preferred = image/urf`、**不支持 PDF**、9100 原始端口关闭。这种机器唯一接受的载荷就是 URF 位图，本工具把「探测 → 渲染 → 编码 → 提交 → 等完成」整条链路做完。

它有两种用法：

- **DSH skill**：放进 `~/.dsh/skills/`，对 agent 说「把这张图打印出来」即可
- **独立 Python CLI**：不依赖 DSH，任何机器上都能直接跑

## 功能

| 命令 | 作用 |
|---|---|
| `selftest` | URF 编解码往返测试，不碰网络 |
| `discover` | mDNS 发现局域网里的 AirPrint 打印机 |
| `probe --host H` | 探测端口、mDNS TXT、WS-Discovery 与 IPP 能力 |
| `status --host H` | 打印机状态、队列、纸张、墨水 |
| `test-page --host H` | 渲染并打印一张诊断页 |
| `print --host H FILE` | 打印图片（png/jpg/webp…） |
| `text --host H TEXT` | 渲染文字并打印（支持中文） |
| `encode / decode` | 图片 ↔ URF，纯本地转换 |

- 自动选择打印机 `document-format-preferred` 的格式，失败时回退其它已声明格式
- 提交后轮询到 `idle` + 队列为空，报告 job-id 和耗时
- 编码后自动解码回读并比对源图，不一致就拒绝打印
- 支持 IPPS（`--tls`，自签名证书可用）
- 中文依赖系统 CJK 字体；没有时自动下载 Noto Sans SC 到 `~/.cache/dsh-airprint/fonts/`（约 8 MB）

## 安装

### 方式一：作为 DSH skill（推荐）

```sh
git clone https://github.com/HeIIoAgain/dsh-airprint-print.git ~/.dsh/skills/airprint-print
```

DSH 的文件系统 skill provider 会监听 `~/.dsh/skills/`，目录克隆完即被发现，新会话就能用。目标目录名必须是 `airprint-print`（与 `SKILL.md` 的 `name` 一致）；如果已存在同名目录，先备份再克隆。

依赖：

```sh
pip3 install --user pillow numpy   # numpy 可选，只影响编码速度
```

### 方式二：独立 CLI

```sh
git clone https://github.com/HeIIoAgain/dsh-airprint-print.git
cd dsh-airprint-print
pip3 install -r requirements.txt
python3 scripts/airprint.py selftest
```

要求 Python ≥ 3.10 和 Pillow；numpy 可选。

## 快速开始

```sh
# 1. 自检（不联网）
python3 scripts/airprint.py selftest

# 2. 找打印机，或探测已知 IP
python3 scripts/airprint.py discover
python3 scripts/airprint.py probe --host 192.168.1.50

# 3. 先 dry-run：只渲染并保存 PNG/URF，不耗纸
python3 scripts/airprint.py test-page --host 192.168.1.50 --dry-run --out /tmp/page.png
python3 scripts/airprint.py test-page --host 192.168.1.50

# 4. 打印图片或文字
python3 scripts/airprint.py print --host 192.168.1.50 photo.jpg --page-size 4x6
python3 scripts/airprint.py text  --host 192.168.1.50 "hello from the LAN" --title "Note"
```

布局重要时一定先跑 `--dry-run`：它会保存渲染后的 PNG 和最终 `.urf` 字节，打开 PNG 检查排版/中文字形即可，不消耗纸张。

作为 DSH skill 使用时不需要敲这些命令，直接对 agent 说「打印这个」「测试一下打印机」「这台打印机为什么打不出来」，agent 会按 [`SKILL.md`](SKILL.md) 的工作流处理。

## 工作原理

1. **探测**：IPP 631 拿 `document-format-supported/preferred`、`urf-supported`、`media-ready`；必要时看 mDNS TXT、WS-Discovery、80/443/515/9100 端口。
2. **渲染**：Pillow 按 `--page-size` / `--dpi` 生成 RGB 位图。
3. **编码**：把位图打包成 URF（PackBits 压缩 + 行头），随后立即解码回读比对，防止编码 bug 打废纸。
4. **提交**：IPP `Print-Job`，等 `printer-state = idle` 且 `queued-job-count = 0`。

## 限制

- **一次一张纸**，没有模拟打印。
- 这类打印机通常只实现 `Print-Job`（`operations-supported = 2`）：**无法查询任务、无法取消**，提交就开始跑。
- 纸张尺寸要匹配，否则可能拒单或走纸异常；`status` 可以看到 `media-ready`。
- TLS 使用打印机自签名证书，工具不做证书校验。
- 远程只能证明「已接受 + 回到 idle」；**纸有没有真的出来只有人能看到**，agent 不应声称做过目视检查。

## 故障排查

| 现象 | 处理 |
|---|---|
| `client-error-document-format-not-supported` (0x040A) | 载荷格式不对；换另一种格式，确认 `urf-supported`，对照 `references/urf-format.md` |
| `client-error-not-found` (0x0406) | `--path` 不对，试 `/ipp` 或 `/` |
| `server-error-not-accepting-jobs` (0x0506) | 打印机忙/暂停/缺纸，先 `status` |
| 端口 631 关闭但 80 开放 | 可能只开了 WSD/EWS，见 `references/troubleshooting.md` |
| 任务一直 `processing` | 缺纸、开盖、墨水错误；看 `printer-state-reasons` |
| 能打但 URF 是乱码 | 编码器/格式问题；跑 `selftest`，对照 `references/urf-format.md` |

完整排障在 [`references/troubleshooting.md`](references/troubleshooting.md)，已实测的打印机特性在 [`references/printer-notes.md`](references/printer-notes.md)。

## 安全建议

- 不要把打印机 631/9100 端口映射到公网；扫描器几小时内就会找到。
- 打印机放在独立 VLAN / IoT 网络，禁止 WAN 入站。
- 不要为了排障擅自开关设备上的 9100/LPD 等服务，可能弄坏别人已有的 Windows/移动端打印队列。
- 不要用猜测的密码登录 EWS；出厂默认密码应及时修改。
- 迭代时默认 `--dry-run`，一次真实打印 = 一张纸 + 墨水。

## 目录结构

```
.
├── SKILL.md                  # DSH 模型侧入口（frontmatter + 工作流）
├── scripts/
│   ├── airprint.py           # CLI：命令、渲染、提交、轮询
│   ├── ipp.py                # IPP 线协议（编码/解码、Print-Job、状态）
│   ├── urf.py                # Apple Raster 编解码（含 numpy 加速路径）
│   ├── render.py             # 页面渲染、字体解析、中文回退
│   └── netprobe.py           # mDNS / WS-Discovery / 端口探测
└── references/
    ├── urf-format.md         # URF 容器布局、PackBits 方言、已知坑
    ├── printer-notes.md      # 实测打印机特性（示例：Brother DCP-T436W）
    └── troubleshooting.md    # 端口、WSD/LPD、安全默认值
```

## 开发与测试

```sh
python3 -m compileall -q scripts     # 语法检查
python3 scripts/airprint.py selftest # 编码往返自检，不联网
```

CI（GitHub Actions）在 Python 3.10 和 3.12 上跑同样的检查，不需要打印机或网络。真实打印只能在有打印机的局域网里验证。

## 许可

[MIT](LICENSE)
