# EON Add-on Repository

A personal Kodi add-on repository, served via GitHub Pages at:

**https://davordragic.github.io/repository.eon**

## What's in here

| Add-on | Description |
|---|---|
| `pvr.eon` | EON.tv PVR client (live TV, EPG, replay/catchup) |
| [`skin.eon`](skin.eon) | EON skin -- a minimal, PVR-first interface built to pair with it |
| [`script.eon.keymap`](script.eon.keymap) | EON Remote Keys -- Down brings up the player OSD instead of skipping ten minutes |

`pvr.eon` is a binary add-on, so it is published once per platform, each in its
own folder: **Android armv7** in [`pvr.eon+android-armv7`](pvr.eon+android-armv7),
**Android arm64** in [`pvr.eon+android-aarch64`](pvr.eon+android-aarch64) and
**macOS arm64** in [`pvr.eon+osx-arm64`](pvr.eon+osx-arm64). There is no
plain `pvr.eon/` folder -- publishing one platform under the bare id would make
it silently privileged (it alone would resolve through Kodi's default
`<id>/<id>-<version>.zip` URL) and the catalog would not show which one it was.
Kodi picks the right one by itself -- each build declares which platform it is
for and Kodi ignores catalog entries that do not match the device it is running
on -- so the install steps below are the same on every device.

Check the current live version at any time:
- Full catalog: https://davordragic.github.io/repository.eon/addons.xml
- Checksum only: https://davordragic.github.io/repository.eon/addons.xml.md5

## Installing on Kodi (once, per device)

This installs the **repository** add-on itself, which then lets Kodi discover
and update everything listed above. Do this on the actual device (e.g. your
Android TV), not on this machine.

1. **Enable installs from zip files**
   Settings → System → Add-ons → turn on **"Unknown sources"** (confirm the warning).

2. **Add this repo as a file source**
   Settings → Media → File manager → **Add source** → enter:
   `https://davordragic.github.io/repository.eon/`
   Name it **`repository.eon`** -- the name is what the source is listed
   under in the next step, so give it the repository's own name rather than
   something you have to remember.

3. **Install the repository add-on from the zip**
   Add-ons → the box icon (bottom left) → **Install from zip file** → select
   the `repository.eon` source → open the `repository.eon/` folder inside it
   → `repository.eon-1.0.3.zip`.
   Wait for the "Add-on installed" notification.

4. **Install add-ons from the repository**
   Add-ons → the box icon → **Install from repository** → **EON Add-on
   Repository** → PVR clients → **EON PVR Client** → **Install**.

5. **Configure the EON PVR Client**
   Open its settings and fill in: service provider, username, password, and
   platform (leave as default unless told otherwise). Then enable it under
   Settings → Player → TV.

   **For seeking/rewind (live TV and replay/catchup) to work**, set
   **"Select Inputstream"** to **`inputstream.ffmpegdirect`** (it defaults to
   `inputstream.adaptive`, which doesn't support seeking with this add-on).
   Make sure the `inputstream.ffmpegdirect` add-on is installed and enabled
   too (Kodi should offer to install it automatically when you switch to it).

6. **Optional: install the EON skin**
   Add-ons → the box icon → **Install from repository** → **EON Add-on
   Repository** → **Look and feel** → **Skin** → **EON** → **Install**, then
   confirm "Keep this skin?" when Kodi switches to it.

   It is a small live-TV-first skin: the home screen is the channel list with
   a live preview and now/next info, the guide is Kodi's own EPG grid, and the
   accent colour is switchable under Settings → Interface → Skin →
   **Colours** (teal, blue, amber, violet). Channel numbers, logos, the
   progress bars and the clock can each be turned off for slower boxes under
   Settings → **Skin settings**.

   To go back to the stock skin: Settings → Interface → Skin → Estuary.

7. **Optional: install EON Remote Keys**
   Add-ons → the box icon → **Install from repository** → **EON Add-on
   Repository** → **Services** → **EON Remote Keys** → **Install**.

   It fixes what Up and Down do while something is playing. Kodi binds them
   to a ten minute skip on a programme opened from the guide -- on a TV remote,
   the two easiest buttons to hit by accident -- and to channel up/down on
   live TV. With this on, **Down brings up the player OSD whatever is playing
   and neither key seeks**; the OSD itself is untouched, so once it is open
   Up/Down/Left/Right move around inside it and Back closes it. The cost is
   zapping with Up and Down on live TV -- use the OSD's channel button or the
   channel list instead.

   It is on by default; the toggle is Add-ons → My add-ons → Services →
   **EON Remote Keys** → **Configure** → **"Down brings up the player OSD"**.
   Switching it off removes the keymap again. Either way the change applies
   immediately -- the add-on reloads the keymap in place, no Kodi restart.

   It works with any skin, including Estuary: a keymap is a Kodi-level file,
   not a skin feature.

## Getting updates / auto-update

Kodi periodically checks `addons.xml` on its own and installs updates for
anything from this repository — no need to repeat the install steps above.
Whether that happens *automatically* vs. just *notifying* you is a **Kodi
device setting**, not something a repository can force from the server side:

- Settings → Add-ons → **"Update add-ons automatically"** — set to "Install
  updates automatically" (this is Kodi's default; check it hasn't been
  changed to "notify only" or "never").
- You can also check per-add-on: Add-ons → My add-ons → PVR clients → EON PVR
  Client → the info panel has its own auto-update toggle, which should be on.

To check immediately instead of waiting for the periodic check:
- Add-ons → My add-ons → PVR clients → EON PVR Client → **Check for update**,
  or restart Kodi, or Settings → Add-ons → **"Check for updates"**.

## Publishing an update (maintainer notes)

`publish.py` is the entry point and always re-emits the **whole** catalog
(`repository.eon`, `pvr.eon`, `script.eon.keymap`, `skin.eon`), because
`create_repository.py` rewrites `addons.xml` from only the add-ons it is
given -- publishing one add-on on its own would silently drop the others:

```
python3 publish.py                                   # re-emit catalog as-is
python3 publish.py --variant-zip ~/pvr.eon+osx-arm64-21.8.5.zip   # ingest a build
```

Nothing in this repository is a working copy of an add-on: every folder here
holds published files only. The sources live **next to this repository**, each
its own git repository so it can be split out entirely later -- the same
arrangement `pvr.eon`'s source has -- and each folder named to sit with the
others rather than after its add-on id:

| Source folder | Git repository | Published into |
|---|---|---|
| `../skin.eon` | `kodi-skin-eon` | `skin.eon/` |
| `../keymap.eon` | `kodi-keymap-eon` | `script.eon.keymap/` |

So the `skin.eon` name collision is only apparent: `../skin.eon` is the source,
`skin.eon/` in here is what got published from it. `publish.py` reads both
sources from those sibling folders and stops with a clear message if either is
missing. `pvr.eon` has no entry because nothing here builds it -- its builds
arrive as finished zips (see below).

To release a skin change, bump `version` in `../skin.eon/addon.xml`, add an
entry at the top of `../skin.eon/changelog.txt`, then run `publish.py`. It
zips the source (skipping `tools/`), writes
`skin.eon/skin.eon-<version>.zip` + `.md5`, copies the changelog and rewrites
`addons.xml` / `addons.xml.md5` and the `index.html` listings.

Before publishing a skin change, run its two dev scripts from `../skin.eon/`:

```
python3 tools/validate.py [path/to/kodi/en_gb/strings.po]   # static checks
python3 tools/make_textures.py                             # regenerate media/
```

`validate.py` is the substitute for a Kodi run: it resolves every include,
texture, font, colour, variable, constant and `$LOCALIZE` id, because Kodi
fails soft on all of those (a typo just leaves part of the screen blank).
`make_textures.py` regenerates every PNG in `../skin.eon/media/`, plus
`icon.png` and `fanart.png`, from the vector definitions in that script -- the
artwork is never hand-edited.

### Releasing an EON Remote Keys change

Bump `version` in `../keymap.eon/addon.xml` and run `publish.py`; it zips the
source into `script.eon.keymap/script.eon.keymap-<version>.zip` + `.md5` and
rewrites the catalog and index pages the same way it does for the skin. There
is no `changelog.txt` in that source yet -- `create_repository.py` copies one
out as `changelog-<version>.txt` the moment there is one to copy, so adding
the file is all it takes.

The add-on exists at all because a keymap cannot ride inside the skin or the
PVR client: Kodi reads keymaps from `special://xbmc/system/keymaps/` and the
two profile directories and nowhere else (`ButtonTranslator.cpp`). A service
add-on that writes one into the profile is the only route a repository has to
a device's key bindings, so that is what `service.py` does -- it syncs
`resources/keymaps/eon-remote.xml` into `special://profile/keymaps/` to match
its own setting, then fires `Action(reloadkeymaps)` so the change lands
without a restart.

### Adding a build for another platform

`pvr.eon` ships one binary per platform. Hand a new build to `publish.py` once
and it is archived in `source/` and re-published from then on:

```
python3 publish.py --variant-zip ~/pvr.eon+osx-arm64-21.8.5.zip
python3 publish.py --variant-zip ~/pvr.eon+android-armv7-21.8.5.zip
```

Every platform gets its own `pvr.eon+<platform>/` folder holding
`pvr.eon-<version>.zip` and a copy of the metadata files, plus its own `<addon>`
entry in `addons.xml` carrying the **same id and version** as the others. That
duplication is deliberate, and is how Kodi serves its own binary add-ons:
`<platform>` makes Kodi discard the entries that do not match the device while
it is parsing `addons.xml`, so the wrong build never reaches its database, and
`<path>` overrides the default `<id>/<id>-<version>.zip` URL so the entry that
does survive still resolves to its own zip. The official
`mirrors.kodi.tv/addons/omega` catalog lists `inputstream.adaptive` six times
per version on exactly this basis.

Because no platform is canonical, `pvr.eon` has no source to hand
`create_repository.py` at all -- that is what `variants_only` on its `ADDONS`
entry means, and why every one of its catalog entries carries a `<path>`.
`--pvr-zip` still works as a deprecated alias for `--variant-zip`, from when the
Android build was the canonical one.

The metadata files are copied into each platform folder rather than shared,
because Kodi resolves an add-on's artwork relative to the folder its `<path>`
points into.

Platform and version are read from each build's own `addon.xml`, never parsed
out of its filename -- platform strings contain hyphens themselves, so
splitting `pvr.eon+osx-arm64-21.8.4.zip` back apart is guesswork. The platform
it declares does have to be one Kodi recognises (`osx-arm64`, `osx-x86_64`,
`android-aarch64`, `windows-x86_64`, ...); an unrecognised string makes the
add-on invisible on every device instead of just the wrong ones.

Note the flip side of that filtering: the armv7 Android build declares
`android-armv7`, which a 64-bit Kodi does **not** accept, and vice versa. Both
Android ABIs are published, so a device is covered either way -- but if one ever
stops offering the PVR client after a Kodi reinstall, check which APK it now
runs (Settings -> System information -> Summary) and make sure the matching
build is still in the catalog.

### Forcing a full re-sync on already-installed devices

If you ever need every device to re-fetch the whole repository (not just pick
up a new add-on version), bump `repository.eon`'s own `version` in
`repository.eon/addon.xml` and run `publish.py`. Kodi treats a version bump of
the repository add-on itself as a reason to re-fetch and re-parse everything
from scratch, which a same-version content edit alone does not reliably
trigger.

### Why there's a `.nojekyll` file and hand-written `index.html` files

GitHub Pages runs everything through Jekyll by default, which auto-renders
`README.md` as the site's `index.html` if no other index file exists — that
replaces the real file listing with rendered prose that has no genuine links,
which makes Kodi's HTTP directory browsing (Add source → Install from zip
file) show up empty. `.nojekyll` disables that, and the `index.html` files at
the root and in each add-on folder provide real `<a href>` listings that
Kodi's file manager can actually parse and browse. `publish.py` rewrites all
of them, so they never need editing by hand.
