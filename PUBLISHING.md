# Publishing

This repository is both a **DSH skill** and a standalone Python CLI. It is not
an npm package: DSH discovers skills from the filesystem, so publishing means
hosting the repository on GitHub.

Repository: <https://github.com/HeIIoAgain/dsh-airprint-print>

## 0. Before you start

```sh
python3 -m compileall -q scripts
python3 scripts/airprint.py selftest
```

Both must pass. `selftest` does not touch the network.

## 1. Create an empty repository on GitHub

1. Open <https://github.com/new>.
2. Owner: `HeIIoAgain`. Repository name: `dsh-airprint-print`.
3. Visibility: public. **Do not** initialize with README, `.gitignore`, or a
   license — the local tree already contains them.
4. Click **Create repository**.

## 2. Push the tree

### Option A — command line (recommended)

```sh
cd dsh-airprint-print

git init -b main
git config user.name "HeIIoAgain"          # only if not configured globally
git config user.email "you@example.com"    # use the email tied to GitHub
git add .
git commit -m "feat: initial public release"

# HTTPS (use a personal access token as the password)
git remote add origin https://github.com/HeIIoAgain/dsh-airprint-print.git

# ...or SSH
# git remote add origin git@github.com:HeIIoAgain/dsh-airprint-print.git

git push -u origin main
```

### Option B — GitHub web upload

<https://github.com/HeIIoAgain/dsh-airprint-print/upload/main> → drag the
extracted `dsh-airprint-print/` contents (not the folder itself) → commit.

Web upload may skip `.github/workflows/`; if the Actions tab stays empty, push
once from the command line or add the workflow files through the web editor.

## 3. Tag a release

```sh
git tag -a v1.0.0 -m "v1.0.0"
git push origin v1.0.0
```

Then open <https://github.com/HeIIoAgain/dsh-airprint-print/releases/new>, pick
the tag, and paste the `1.0.0` section of [CHANGELOG](CHANGELOG.md).

## 4. Install from GitHub

As a DSH skill (note the target directory name must be `airprint-print`):

```sh
git clone https://github.com/HeIIoAgain/dsh-airprint-print.git ~/.dsh/skills/airprint-print
```

DSH watches `~/.dsh/skills/`, so no restart is needed; the next session catalog
includes the skill. To pin a version, clone a tag or a commit SHA instead of the
default branch.

As a standalone CLI:

```sh
git clone https://github.com/HeIIoAgain/dsh-airprint-print.git
cd dsh-airprint-print
pip3 install -r requirements.txt
python3 scripts/airprint.py selftest
```

## 5. After publishing

- Actions tab: the `CI` workflow runs `compileall` and `selftest` on Python 3.10
  and 3.12 for every push and pull request.
- If the skill does not appear in DSH, confirm the directory is
  `~/.dsh/skills/airprint-print/` and contains `SKILL.md` at its root, and that
  `SKILL.md` frontmatter has `name: airprint-print`.
- Re-check that examples still use documentation IPs (`192.168.1.50`) and never
  a real device address before publishing.
