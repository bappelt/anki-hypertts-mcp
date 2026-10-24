---
name: release
description: Cut a versioned release of the HyperTTS MCP Bridge - finalize CHANGELOG.md, bump the version in mcp_server/package.json, commit, tag v<version>, push, and watch GitHub Actions publish the .ankiaddon and .mcpb as a GitHub Release. Use when asked to release, ship, publish, cut, or tag a new version.
argument-hint: "[version | patch | minor | major]"
disable-model-invocation: true
---

# Release the HyperTTS MCP Bridge

A release here is driven entirely by a git tag. Pushing `v<version>` makes
`.github/workflows/build.yml` build both packages and publish them as a
GitHub Release. Your job is to get the repository into the right state, push
the tag, and confirm the release actually came out with both files.

`version` in `mcp_server/package.json` is the single source of truth. The
build scripts, the bundle manifest and the MCP server all read it from there,
and the workflow refuses a tag that doesn't equal `v` + that version. A release
commit changes only `package.json` (plus `package-lock.json`, which
`npm version` keeps in sync) and `CHANGELOG.md`, whose section for the
version becomes the GitHub release notes. The workflow also refuses a tag
with no matching `## [<version>]` changelog section. DEVELOPMENT.md >
Versioning has the background.

## 1. Preflight

Run these checks before changing anything. Releasing from a messy state ships
something other than what's on `main`, so stop and tell the user if a check
fails rather than working around it.

```bash
git fetch --tags origin
git branch --show-current                  # must be main
git status --porcelain                     # must be empty
git rev-list --left-right --count main...origin/main   # must be "0	0"
gh auth status
```

Then gather what you need to pick the version:

```bash
node -p "require('./mcp_server/package.json').version"   # current version
git describe --tags --abbrev=0 2>/dev/null || echo "(no releases yet)"
git log --oneline "$(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)"..HEAD
```

If there are no commits since the last tag, there is nothing to release; say
so and stop.

Read the `## [Unreleased]` section of `CHANGELOG.md`. It should already
describe the changes in those commits. If it's empty or misses something
user-visible, draft the missing entries from the commits now; you'll show
them to the user with the version in the next step.

The changelog records changes between releases, not the product's
features. For the first release, the section is just "Initial release." —
don't draft entries from the history before it.

## 2. Choose the version

The argument may be an explicit version (`0.2.0`, `0.2.0-beta.1`), a bump
keyword (`patch`, `minor`, `major`), or absent.

- **No releases yet:** the first release is the current `package.json`
  version as-is (no bump), unless the user asked for something else.
- **Keyword:** apply it to the current version.
- **Absent:** propose a version from the commits since the last tag, using
  semver as it applies to this project's users:
  - **major** — something a user must act on: a removed or renamed MCP tool
    or tool argument, a changed HTTP endpoint, a config key that no longer
    works, or a raised minimum Anki/HyperTTS version.
  - **minor** — new capability: a new tool, argument, endpoint or config
    option.
  - **patch** — fixes, docs, CI, internal refactors.

  While the version is below 1.0.0, put breaking changes in a minor bump
  rather than jumping to 1.0.0; that's the usual semver convention for
  pre-1.0 projects, and going to 1.0.0 is the user's call.

The new version must be valid semver, higher than the current one, and its
tag must not exist yet (`git tag -l v<version>` and
`git ls-remote --tags origin v<version>` both empty). A hyphenated version
like `0.2.0-beta.1` is published as a prerelease; mention that if you pick
one.

**Confirm with the user before going further**, unless they gave an explicit
version in this request and the Unreleased section needed no additions. Show
the proposed version, why, the commit list it covers, and the release notes
(the Unreleased entries, including any you drafted). Pushing a tag publishes a release, which is visible to anyone with
repo access and awkward to retract.

## 3. Local sanity check

CI builds everything anyway, but catching a broken build before tagging
avoids a failed run and a dangling tag:

```bash
python3 -m py_compile anki_addon/__init__.py
node --check mcp_server/index.js
python3 build_addon.py
```

Skip `mcpb/build.sh` here; it's slow and needs the network, and CI runs it
before the release job.

## 4. Update the changelog

Edit `CHANGELOG.md` in Keep a Changelog style:

- Rename `## [Unreleased]` to `## [<version>] - <YYYY-MM-DD>` (today's
  date), and put a new, empty `## [Unreleased]` above it.
- Write entries for users, not as a commit log. Use the standard groups:
  Added, Changed, Deprecated, Removed, Fixed, Security. Leave out changes
  users can't notice, such as CI, refactors, and maintainer docs.
- Update the link references at the bottom:
  `[Unreleased]: https://github.com/bappelt/anki-hypertts-mcp/compare/v<version>...HEAD`,
  and for the new version either
  `[<version>]: https://github.com/bappelt/anki-hypertts-mcp/compare/v<previous>...v<version>`
  or, for the first release,
  `[<version>]: https://github.com/bappelt/anki-hypertts-mcp/releases/tag/v<version>`.

## 5. Bump, commit, tag, push

```bash
(cd mcp_server && npm version <version> --no-git-tag-version)
git add mcp_server/package.json mcp_server/package-lock.json CHANGELOG.md
git commit -m "Release v<version>"     # plus any attribution trailer this session requires
git tag -a v<version> -m "v<version>"
git push origin main
git push origin v<version>
```

`--no-git-tag-version` matters: npm would otherwise commit and tag on its own
from inside `mcp_server/`, with its own message. Push `main` before the tag
so the release's generated notes and the tagged commit are both on `main`.

If the release version already equals the current `package.json` version
(the first release), skip the `npm version` step; `npm version` errors when
the version doesn't change. The commit then contains only `CHANGELOG.md`.

If `package-lock.json` changed anything besides the version fields, stop and
show the user the diff; a release shouldn't silently change dependencies.

## 6. Watch the workflow

The tag push starts a run whose branch is the tag name:

```bash
run_id=$(gh run list --workflow build.yml --branch v<version> --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$run_id" --exit-status
```

The run may take a few seconds to appear after the push; retry the
`gh run list` briefly if it comes back empty.

## 7. Verify the release

```bash
gh release view v<version> --json url,isPrerelease,assets --jq '{url, isPrerelease, assets: [.assets[].name]}'
```

It should list exactly two assets: `hypertts_mcp_bridge-<version>.ankiaddon`
and `hypertts-mcp-bridge-<version>.mcpb`, and its notes should match the
changelog section. Report the release URL, the version, whether it's a
prerelease, and the asset names.

Then hand off the AnkiWeb step, which you can't do: AnkiWeb has no upload
API. Tell the user to follow DEVELOPMENT.md > Publishing to AnkiWeb, and
point out whether `ankiweb_description.html` changed in this release, since
the listing's description has to be pasted in by hand.

Remind the user that installed copies don't update themselves: Claude Desktop
needs the new `.mcpb` installed, and Anki needs the new `.ankiaddon` installed
(Tools > Add-ons > Install from file) followed by a restart.

## If the workflow fails

No release is created when the build job fails, but the tag and the version
commit are already pushed. Show the user the failing step's log
(`gh run view <run_id> --log-failed`) and explain the cause.

Don't delete or move the tag on your own: deleting a pushed tag is
destructive, and someone may already have fetched it. Offer the options and
let the user choose:

- **Fix forward (usually best):** fix the problem, then release the next
  patch version.
- **Retag:** delete the tag (`git push --delete origin v<version>` and
  `git tag -d v<version>`), fix, then tag the fixed commit with the same
  version. Only sensible if nobody could have used the failed tag.
