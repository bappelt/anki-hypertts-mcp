---
name: release
description: Cut a versioned release of the HyperTTS MCP Bridge, end to end - check the AnkiWeb listing, finalize CHANGELOG.md, bump the version in mcp_server/package.json, tag v<version>, watch GitHub Actions publish the .ankiaddon and .mcpb as a GitHub Release, then upload the add-on to AnkiWeb through the user's browser. Use when asked to release, ship, publish, cut, or tag a new version, or to update the add-on on AnkiWeb.
argument-hint: "[version | patch | minor | major]"
disable-model-invocation: true
---

# Release the HyperTTS MCP Bridge

A release has two destinations, and it isn't done until both have the new
version:

1. **GitHub Release**, driven entirely by a git tag. Pushing `v<version>`
   makes `.github/workflows/build.yml` build both packages and publish them,
   with the version's `CHANGELOG.md` section as the notes.
2. **AnkiWeb**, where most Anki users get add-ons. AnkiWeb has no upload API,
   so the `.ankiaddon` goes up through its web form, in the user's own
   logged-in browser.

`version` in `mcp_server/package.json` is the single source of truth. The
build scripts, the bundle manifest and the MCP server all read it from there,
and the workflow refuses a tag that doesn't equal `v` + that version, or that
has no `## [<version>]` changelog section. DEVELOPMENT.md > Versioning has
the background.

Two files describe the AnkiWeb listing, so nothing about it is invented at
release time:

- `ankiweb_description.html`: the listing's description, pasted into the form.
- `ankiweb.json`: the other form fields, and the add-on's AnkiWeb id once it
  exists (`addon_id` is `null` until the first upload).

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

## 2. Check the AnkiWeb listing

The listing makes claims that drift as the code changes, and fixing them now
means the fixes ride along in the release commit instead of needing a
follow-up. Read `ankiweb_description.html` and `ankiweb.json` and check them
against the code being released:

- **Tools:** the tools and what they do match `mcp_server/index.js`.
- **Config:** the settings listed match `anki_addon/config.json`, with the
  same defaults.
- **HyperTTS version:** "Tested with HyperTTS ..." matches the newest version
  in DEVELOPMENT.md > Test history.
- **Minimum Anki:** the listing's "Requires Anki ..." and
  `min_anki_version` match `min_point_version` in `build_addon.py`
  (`231000` is `23.10`).
- **Tested Anki:** `max_anki_version_tested` is the newest Anki this release
  was tested on. The user's installed version is in the folder name of
  `~/Library/Application Support/AnkiProgramFiles/.venv/lib/python3.*/site-packages/aqt-*.dist-info`;
  AnkiWeb writes `25.9.4` as `25.09.4`. Only raise it if the user has run
  this release on that version.
- **Encoding:** the description must stay ASCII (use `&rarr;` and similar
  entities), because a non-ASCII arrow was once garbled into `â†’`. Check
  with `LC_ALL=C grep -n '[^ -~]' ankiweb_description.html`, which prints
  nothing when the file is clean.
- **Title:** under 80 characters, ASCII.

Collect any corrections; you'll show them with the version and apply them in
step 5.

## 3. Choose the version

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
like `0.2.0-beta.1` is published as a prerelease on GitHub. AnkiWeb has no
prereleases, so skip the AnkiWeb step for those and say so.

**Confirm with the user before going further**, unless they gave an explicit
version in this request and neither the changelog nor the listing needed
changes. Show the proposed version and why, the commits it covers, the
release notes (including any entries you drafted), and any listing
corrections. Pushing a tag publishes a release that anyone can see.

## 4. Local sanity check

CI builds everything anyway, but catching a broken build before tagging
avoids a failed run and a dangling tag:

```bash
python3 -m py_compile anki_addon/__init__.py
node --check mcp_server/index.js
python3 build_addon.py
```

Skip `mcpb/build.sh` here; it's slow and needs the network, and CI runs it
before the release job.

## 5. Update the changelog and listing

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

Apply the listing corrections from step 2 to `ankiweb_description.html` and
`ankiweb.json`.

## 6. Bump, commit, tag, push

```bash
(cd mcp_server && npm version <version> --no-git-tag-version)
git add mcp_server/package.json mcp_server/package-lock.json CHANGELOG.md ankiweb_description.html ankiweb.json
git commit -m "Release v<version>"     # plus any attribution trailer this session requires
git tag -a v<version> -m "v<version>"
git push origin main
git push origin v<version>
```

`--no-git-tag-version` matters: npm would otherwise commit and tag on its own
from inside `mcp_server/`, with its own message. Push `main` before the tag
so the tagged commit is on `main`.

If the release version already equals the current `package.json` version
(the first release), skip the `npm version` step; `npm version` errors when
the version doesn't change.

If `package-lock.json` changed anything besides the version fields, stop and
show the user the diff; a release shouldn't silently change dependencies.

## 7. Watch the workflow

The tag push starts a run whose branch is the tag name:

```bash
run_id=$(gh run list --workflow build.yml --branch v<version> --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$run_id" --exit-status
```

The run may take a few seconds to appear after the push; retry the
`gh run list` briefly if it comes back empty.

## 8. Verify the GitHub Release

```bash
gh release view v<version> --json url,isPrerelease,assets --jq '{url, isPrerelease, assets: [.assets[].name]}'
```

It should list exactly two assets: `hypertts_mcp_bridge-<version>.ankiaddon`
and `hypertts-mcp-bridge-<version>.mcpb`, and its notes should match the
changelog section.

## 9. Publish to AnkiWeb

Upload the exact file from the GitHub Release, not a local rebuild, so
AnkiWeb and GitHub serve the same build:

```bash
rm -rf dist/ankiweb && gh release download v<version> -p '*.ankiaddon' -D dist/ankiweb
```

Which page to use depends on `addon_id` in `ankiweb.json`:

- **`null` (first upload):** `https://ankiweb.net/shared/upload`, which
  creates a new listing.
- **Set:** `https://ankiweb.net/shared/upload?id=<addon_id>`, the same form
  pre-filled with the existing listing. Using the plain upload page here
  would create a duplicate listing.

### With the Claude in Chrome browser tools

Use these when they're available; load the claude-in-chrome skill first.

1. Open the page in a new tab. If AnkiWeb shows a login page instead of the
   form, stop and ask the user to log in themselves; never type their
   credentials.
2. Fill the form from `ankiweb.json`. The form's fields, top to bottom:
   - **Title**, **Tags**, **Support Page**: text boxes. On an update, check
     them against `ankiweb.json` and correct any that differ.
   - **Branches**: on a first upload, click **Add New Branch**. Branch 1 has
     two version boxes: set the first to `min_anki_version` and the second to
     `max_anki_version_tested`. Don't prefix the maximum with `-`; that
     would block the add-on on newer Anki versions rather than marking what
     it was tested on.
   - **Upload file**: choose Branch 1 in the dropdown, then attach
     `dist/ankiweb/hypertts_mcp_bridge-<version>.ankiaddon` to the file
     input with the file upload tool.
   - **Description**: replace the whole text box with the contents of
     `ankiweb_description.html`.
3. **Don't click Save yet.** Take a screenshot and show the user the filled
   form: title, tags, support page, branch versions, the attached file name,
   and that the description is the current listing. Ask for an explicit go-
   ahead. Saving publishes the add-on to every AnkiWeb user, so this is the
   user's call even though they started the release.
4. On a yes, click **Save**. AnkiWeb then shows the add-on's info page, at
   `https://ankiweb.net/shared/info/<id>`.
5. Verify that page: "Updated" shows today's date, "Supported Anki versions"
   shows the branch range, and the description renders with arrows, not
   `â†’`. If something is wrong, tell the user and go back through the
   update page; don't remove the add-on.
6. Close the tab.

### Without browser tools

Give the user a checklist instead: the page to open, every field value from
`ankiweb.json`, the file path in `dist/ankiweb/`, and a reminder to paste in
`ankiweb_description.html` as the description. Ask them to tell you the
info page URL afterwards, so you can do step 10.

## 10. Record the AnkiWeb id (first upload only)

After the first upload, the info page URL holds the new add-on's id. Record
it so every later release updates this listing rather than creating another:

- Set `addon_id` in `ankiweb.json` to the id, as a string.
- In `README.md`, add an AnkiWeb option to the add-on install steps: Tools
  &rarr; Add-ons &rarr; Get Add-ons, and paste the code `<id>`, with a link to
  the info page. Keep the `.ankiaddon` file option as the alternative.

Commit as "Record AnkiWeb add-on id" and push. This happens after the tag,
so it isn't part of the release itself, which is fine: it's metadata about
where the release lives.

## 11. Report

Report the GitHub Release URL, the AnkiWeb info page URL, the version,
whether it's a prerelease, and the asset names.

Remind the user that installed copies don't update themselves: Claude Desktop
needs the new `.mcpb` installed. For Anki, users who installed from AnkiWeb
get the update through Tools &rarr; Add-ons &rarr; Check for Updates. A copy
installed from a `.ankiaddon` file is a separate add-on to Anki (it lives in
a different folder), so the user shouldn't keep both enabled; two bridges
would compete for the same port.

## If the workflow fails

No release is created when the build job fails, but the tag and the version
commit are already pushed. Show the user the failing step's log
(`gh run view <run_id> --log-failed`) and explain the cause. Don't upload
anything to AnkiWeb.

Don't delete or move the tag on your own: deleting a pushed tag is
destructive, and someone may already have fetched it. Offer the options and
let the user choose:

- **Fix forward (usually best):** fix the problem, then release the next
  patch version.
- **Retag:** delete the tag (`git push --delete origin v<version>` and
  `git tag -d v<version>`), fix, then tag the fixed commit with the same
  version. Only sensible if nobody could have used the failed tag.

## If the AnkiWeb upload fails

The GitHub Release is already out and stays valid; only AnkiWeb is behind.
Tell the user what AnkiWeb said, and retry from step 9 once it's fixed. A
rejected upload changes nothing on AnkiWeb, so retrying is safe.
