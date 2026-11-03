# v1.0.0 — 首个公开版本

> **English summary:** Print to AirPrint / Mopria printers that only speak Apple
> Raster (URF) — no CUPS, no driver, no root. Probe → render → encode → submit → wait.

针对一类很常见的便宜网络打印机：只开 IPP 631、只认 `image/urf`、**不支持 PDF**、9100 原始端口关闭。
这类机器唯一接受的载荷就是 URF 位图，本工具把整条链路做完了。

## 亮点

- **无 CUPS、无驱动、零 root**：只依赖 Pillow，直接拼 IPP `Print-Job` 报文
- **一次一张纸，但不打废纸**：编码后自动解码回读比对源图，不一致直接拒绝打印
- **格式自动协商**：优先用打印机 `document-format-preferred`，被拒（0x040A）自动回退其它声明格式
- **提交后盯着打完**：轮询到 `printer-state = idle` 且队列为空，报告 job-id 与耗时
- **先看再打**：`--dry-run` 只渲染并保存 PNG + `.urf` 字节，不耗纸，排版不对先改
- **中文可打**：系统有 CJK 字体就用，没有就自动下载一次 Noto Sans SC 到 `~/.cache/dsh-airprint/fonts/`
- **IPPS 支持**：`--tls` 走 443，接受自签名证书
- **两种用法一套代码**：DSH 技能（放进 `~/.dsh/skills/`）+ 独立 Python CLI

## 命令一览

| 命令 | 作用 |
|---|---|
| `selftest` | URF 编解码往返自检，不碰网络 |
| `discover` | mDNS 发现局域网 AirPrint 打印机 |
| `probe --host H` | 端口 / mDNS TXT / WS-Discovery / IPP 能力 |
| `status --host H` | 状态、队列、纸张、墨水 |
| `test-page --host H` | 渲染并打印诊断页 |
| `print --host H FILE` | 打印图片（png/jpg/webp…） |
| `text --host H TEXT` | 渲染文字并打印（支持中文） |
| `encode` / `decode` | 图片 ↔ URF，纯本地转换 |

## 安装

作为 DSH 技能（目录名必须是 `airprint-print`）：

```sh
git clone https://github.com/HeIIoAgain/dsh-airprint-print.git ~/.dsh/skills/airprint-print
pip3 install --user pillow   # numpy 可选，只影响编码速度
```

作为独立 CLI：

```sh
git clone https://github.com/HeIIoAgain/dsh-airprint-print.git
cd dsh-airprint-print
pip3 install -r requirements.txt
python3 scripts/airprint.py selftest
```

要求 Python ≥ 3.10 与 Pillow。

## 30 秒验证（没有打印机也能跑）

```sh
python3 -m compileall -q scripts
python3 scripts/airprint.py selftest
# 期望输出：round trip: OK ... selftest passed
```

CI 在 Ubuntu / Windows / macOS 的 Python 3.10 与 3.12 上跑同样的两步，不需要打印机或网络。

## 已知限制（来自设备协议，不是实现偷懒）

- 一次一张纸，没有模拟打印
- 这类打印机通常只实现 `Print-Job`（`operations-supported = 2`）：**无法查询任务、无法取消**
- 纸张尺寸必须匹配，否则可能拒单或走纸异常
- 远程只能证明「已接受 + 回到 idle」，**纸有没有真出来只有人能看到**
- TLS 不校验证书（打印机是自签名的）

## 实测环境

Brother DCP-T436W（特性记录见 `references/printer-notes.md`）。其它机型的适配情况欢迎提 Issue 补充。

## 许可

MIT。非官方项目，与 Apple / 各打印机厂商无关联。

---

**Full Changelog**: https://github.com/HeIIoAgain/dsh-airprint-print/blob/main/CHANGELOG.md
