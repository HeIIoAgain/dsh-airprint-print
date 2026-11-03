# dsh-airprint-print 上架收尾清单

按顺序做，大约 15 分钟。每步都有验收标准。

生成的文件在 `airprint-publish/` 下，目标仓库是
https://github.com/HeIIoAgain/dsh-airprint-print

---

## 步骤 1 · 补两个文件到仓库根目录

把下面两个文件**原样**拷进仓库（保持相对路径）：

| 本地产物 | 放到仓库的位置 |
|---|---|
| `airprint-publish/.gitignore` | `<仓库根>/.gitignore` |
| `airprint-publish/.github/workflows/ci.yml` | `<仓库根>/.github/workflows/ci.yml` |

> 只加这两个文件即可。README、PUBLISHING.md、CHANGELOG 里写的「CI 在 3.10/3.12 跑
> compileall + selftest」原本是空的，加上 `ci.yml` 之后三处描述**同时变成事实**，文档不用改。

### 如果用网页操作（注意）

GitHub 网页的 **Upload files** 拖拽上传**会拒绝** `.github/workflows/` 下的文件。要用：

1. 仓库页 → **Add file ▾ → Create new file**
2. 文件名输入 `.github/workflows/ci.yml`（输入 `/` 会自动建目录）
3. 粘贴 `ci.yml` 全文 → **Commit changes**

`.gitignore` 同样用 Create new file 输入 `.gitignore` 即可。

### 建议的 commit 信息（用命令行 push 时）

```sh
git add .gitignore
git commit -m "chore: 忽略 __pycache__、本地渲染产物与密钥文件"

git add .github/workflows/ci.yml
git commit -m "ci: 在 Ubuntu/Windows/macOS 的 Python 3.10/3.12 上跑 compileall 与 URF 自检"

git push
```

**验收**：仓库 **Actions** 标签页出现一次 `CI` 运行，4 个 job 全绿（约 1 分钟）。

---

## 步骤 2 · 加 topics

网页：仓库首页右侧 **About** 旁的 ⚙ → **Topics** 输入框 → **每输入一个按回车** → `Save changes`。

建议这 11 个。选法是**跟着两个真正的同行项目借流量**：`apple/cups`（2165★）和
`michaelrsweet/pappl`（350★）挂的就是这套标签，挂同样的标签，你的仓库会出现在它们的
"相关仓库"里：

| topic | 依据 |
|---|---|
| `airprint` | pappl 在用；品类主词 |
| `ipp` | cups 在用；177 个仓库 |
| `ipp-protocol` | cups 在用 |
| `printer` | cups 在用；大词，曝光主力 |
| `printing` | cups 在用；大词，曝光主力 |
| `apple-raster` | pappl 在用；只有 2 个仓库，但 100% 对口 |
| `ippeverywhere` | pappl 在用，同一技术圈 |
| `pwg-raster` | pappl 在用；相邻格式，同圈读者会点进来 |
| `python` | 语言词，必挂 |
| `windows` | 目标平台 |
| `deepseek-harness` | 你自己的生态，四个仓库互相导流 |

**不要用**这两个（已核实）：

- `urf`：17 个仓库里绝大多数是 .NET 的 "Unit of Work & Repositories Framework"，
  同名不同义，挂上去等于把自己扔进垃圾堆；
- `no-driver`：只有 2 个仓库，内容无关（一个蓝牙遥控器项目）。

命令行等价（`gh auth login` 之后）：

```bash
gh repo edit HeIIoAgain/dsh-airprint-print \
  --add-topic airprint,ipp,ipp-protocol,printer,printing,apple-raster,ippeverywhere,pwg-raster,python,windows,deepseek-harness
```

**验收**：刷新首页，About 面板底部出现这些标签。

---

## 步骤 3 · 打 tag + 建 Release

```sh
git tag -a v1.0.0 -m "v1.0.0 — 首个公开版本"
git push origin v1.0.0
```

然后：

1. 打开 https://github.com/HeIIoAgain/dsh-airprint-print/releases/new
2. **Choose a tag** 选刚推的 `v1.0.0`
3. 标题填 `v1.0.0 — 首个公开版本`
4. 正文粘贴 `airprint-publish/RELEASE-v1.0.0.md` 全文
5. 勾 **Set as the latest release** → **Publish release**

> 纯网页也行：Releases → **Draft a new release** → 在 Choose a tag 里输入 `v1.0.0` 并选
> "Create new tag on publish"。效果一样。

**验收**：Release 页显示 v1.0.0；`git tag` 能列出 `v1.0.0`。

---

## 步骤 4（可选，5 分钟）· 加三个 badge

README 目前**一个 badge 都没有**。在两个 README 的 H1 下方空一行插入：

```markdown
[![CI](https://github.com/HeIIoAgain/dsh-airprint-print/actions/workflows/ci.yml/badge.svg)](https://github.com/HeIIoAgain/dsh-airprint-print/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](requirements.txt)
```

`README.md` 和 `README.en.md` 都加，内容相同。

**验收**：CI 跑过一次之后，第一个 badge 显示 `CI passing`（不是 `no status`）。

---

## 最终验收清单

- [ ] Actions 页有绿的 `CI` 运行，4 个 job 通过
- [ ] 仓库首页 About 显示 11 个 topics
- [ ] Releases 页有 `v1.0.0`（Latest）
- [ ] `git log --oneline` 至少 3 条提交，不再是单条 `V1.0`
- [ ] `git status` 干净，没有 `scripts/__pycache__/` 被跟踪
- [ ] clone 到新目录后 `python3 scripts/airprint.py selftest` 输出 `selftest passed`

---

## 我顺手发现的两个代码问题（不急，但别忘）

### 1. `test-page` 会偷偷下载 8 MB 字体

`scripts/render.py` 的 `test_page()` 里有这一行：

```python
draw.text((margin, round(4100 * sy)),
          _localize("— end of test page —", "— 测试页结束 —"),
          font=font("regular", round(80 * s), "测试页"), fill=LIGHT)
```

**显示的文字**已经按 `has_cjk_font()` 做了本地化（没字体就画英文），但**选字体时**却硬编码传了
`"测试页"` → 触发 `needs_cjk()` → 走到 `ensure_cjk_font()` → 下载字体。

后果：在**没有 CJK 字体的机器**（精简 Linux、容器、CI runner）上，哪怕只打一张全英文测试页，
也会先静默下载 8 MB 字体。Windows 用户一般碰不到（有 `msyh.ttc`）。

修法（一行）：把选字体的文本改成和显示文本同一个变量：

```python
end_text = _localize("— end of test page —", "— 测试页结束 —")
draw.text((margin, round(4100 * sy)), end_text,
          font=font("regular", round(80 * s), end_text), fill=LIGHT)
```

### 2. 没有 `tests/` 目录，CI 只能跑自检

`selftest` 只覆盖 URF 编解码往返，`ipp.py` 的报文编解码、`netprobe.py` 的解析、`render.py` 的
排版都没有测试。下一步值得补的是 `tests/test_urf.py`、`tests/test_ipp.py`（纯字节解析，不需要
打印机和网络），CI 里加一行 `pytest -q`。需要我写就说一声。
