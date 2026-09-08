#!/usr/bin/env python3
"""Publish this repository's full add-on catalog from source.

create_repository.py rewrites addons.xml from ONLY the add-ons passed on
its command line, so every publish must pass every add-on we ever want
listed -- a run that publishes just one add-on would silently drop the
others out of the catalog. ADDONS below is that single source of truth;
running this script with no arguments re-emits the whole catalog from
current sources, and passing --variant-zip additionally ingests a freshly
built per-platform binary, such as a new pvr.eon release.

Usage:
    publish.py                                  # re-emit catalog as-is
    publish.py --variant-zip /path/to/pvr.eon+osx-arm64-X.Y.Z.zip
    publish.py --variant-zip /path/to/pvr.eon+android-armv7-X.Y.Z.zip
"""
import argparse
import contextlib
import hashlib
import dataclasses
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent
SOURCE_DIR = REPO_ROOT / "source"
SKIN_SOURCE = REPO_ROOT.parent / "skin.eon"
KEYMAP_SOURCE = REPO_ROOT.parent / "keymap.eon"

# The metadata files create_repository.py copies next to each zip, in the
# order the generated index pages list them. addon.xml is always there;
# these are optional. Both fanart extensions appear because Kodi resolves
# an add-on's <assets> against the datadir -- pvr.eon declares fanart.jpg,
# skin.eon declares fanart.png, and whichever one is not copied out here
# is a 404 on the add-on's info screen.
OPTIONAL_ASSETS = ("icon.png", "fanart.jpg", "fanart.png", "LICENSE.txt")


@dataclasses.dataclass
class Addon:
    id: str
    keep: int
    # (args) -> pathlib.Path (a folder or a zip file). Unused, and may be None,
    # when variants_only is set: there is no single source to hand over.
    locate: "callable" = None
    ignore: tuple = ()  # shutil.ignore_patterns() patterns, folders only
    # Publish every source/<id>+<platform>-<version>.zip build as a platform
    # variant of this add-on. See publish_variant().
    variants: bool = False
    # This add-on exists ONLY as per-platform builds, so it has no source to
    # give create_repository.py and no plain <id>/ folder: every build lives in
    # its own <id>+<platform>/ folder and every catalog entry carries a <path>.
    # Kodi is fine with that -- it filters on <platform> while parsing
    # addons.xml, so a device only ever sees the one entry that fits it.
    variants_only: bool = False


def version_key(v):
    """Sort key for 'MAJOR.MINOR.PATCH[-~+SUFFIX]' versions, newest first
    with reverse=True. A prerelease sorts just below its matching final
    release rather than crashing int() on the suffix."""
    core = re.split(r"[-~+]", v, maxsplit=1)[0]
    is_final = core == v
    return tuple(int(p) for p in core.split(".")) + (1 if is_final else 0,)


def locate_repository_eon(args):
    return REPO_ROOT / "repository.eon"


def locate_script_eon_keymap(args):
    """Source tree beside this repository, the same arrangement the skin and
    the client have, and named to sit with them: keymap.eon next to pvr.eon
    and skin.eon, in a git repository called kodi-keymap-eon exactly as
    skin.eon lives in kodi-skin-eon. The published folder is neither of those
    names -- it is REPO_ROOT/"script.eon.keymap", after the add-on id."""
    location = KEYMAP_SOURCE
    if not location.is_dir():
        sys.exit(f"Keymap add-on source not found at {location} -- publish.py "
                 f"expects it as a sibling of this repository")
    return location


def locate_script_eon_defaults(args):
    """Unlike the keymap and the skin, this one's source lives inside this
    repository rather than in a sibling checkout -- the same arrangement the
    repository add-on itself uses. It is small enough that a checkout of its
    own would be more ceremony than it earns; move it out and only this
    function changes."""
    return REPO_ROOT / "script.eon.defaults"


def locate_skin_eon(args):
    """The skin's source tree, which sits next to this repository rather than
    inside it -- the same arrangement pvr.eon's source has. Note the name
    collision is only apparent: REPO_ROOT/"skin.eon" is the *published* folder,
    this is the source."""
    location = SKIN_SOURCE
    if not location.is_dir():
        sys.exit(f"Skin source not found at {location} -- publish.py expects it "
                 f"as a sibling of this repository")
    return location


# Every entry here is passed to create_repository.py on EVERY run. Adding
# an add-on: append it here. Nothing else needs to change to keep it in
# the published catalog going forward.
ADDONS = [
    # index.html is excluded because rewrite_index() regenerates it *after*
    # create_repository.py has already built the zip: shipping it would embed
    # a listing that is permanently one publish out of date, and would change
    # the zip's checksum on every run for content that never differs.
    # keep=1, unlike everything else here: this folder is what a new device
    # browses to bootstrap itself, so a second version sitting in the listing
    # is a wrong zip one row away from the right one. Rolling the repository
    # add-on back is not worth that -- a device on a broken repository version
    # cannot self-update out of it anyway, so the recovery is the same manual
    # install-from-zip either way, and the fix ships as a version bump.
    Addon(id="repository.eon", keep=1, locate=locate_repository_eon,
          ignore=("*.zip", "*.zip.md5", "index.html")),
    # pvr.eon is a binary add-on: one build per platform and no platform-
    # neutral build to treat as canonical, so every platform gets its own
    # pvr.eon+<platform>/ folder and there is no plain pvr.eon/ at all.
    # Publishing one of them under the bare id would have made that platform
    # silently privileged -- it alone would resolve through Kodi's default
    # <id>/<id>-<version>.zip URL -- and reading the catalog would not show
    # which one it was.
    Addon(id="pvr.eon", keep=2, variants=True, variants_only=True),
    # The skin is built from its own source tree beside this repository (see
    # locate_skin_eon); skin.eon/ here holds only what gets published. tools/ is
    # developer scripts, not part of the add-on.
    # .git matters now that the skin source is its own repository: without it
    # the whole history would be zipped into the add-on and shipped.
    # A keymap cannot travel inside a skin or a binary add-on: Kodi reads them
    # from system/keymaps and the two profile directories and nowhere else (see
    # ButtonTranslator.cpp). This add-on exists to carry one into the profile,
    # which is the only route a repository has to a device's key bindings.
    Addon(id="script.eon.keymap", keep=2, locate=locate_script_eon_keymap,
          ignore=(".git", ".gitignore", ".DS_Store", "__pycache__", "*.pyc",
                  "*.zip", "*.zip.md5", "index.html")),
    # Sets Kodi's own guide settings, which neither a skin nor a binary PVR
    # client can reach: the add-on API only exposes an add-on's own settings,
    # and skins have no builtin for a system setting. Imported by skin.eon so
    # installing the skin brings it along.
    Addon(id="script.eon.defaults", keep=2, locate=locate_script_eon_defaults,
          ignore=(".git", ".gitignore", ".DS_Store", "__pycache__", "*.pyc",
                  "*.zip", "*.zip.md5", "index.html")),
    Addon(id="skin.eon", keep=2, locate=locate_skin_eon,
          ignore=(".git", ".gitignore", ".DS_Store", "tools", "__pycache__",
                  "*.zip", "*.zip.md5")),
]


def zip_addon_root(zip_path):
    """The <addon> element out of a zip's addon.xml, plus the name of the
    zip's single top-level folder (the metadata files sit next to addon.xml
    inside it)."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.rsplit("/", 1)[-1] == "addon.xml"]
        if not names:
            raise RuntimeError(f"No addon.xml found in {zip_path}")
        name = min(names, key=len)
        return ET.fromstring(zf.read(name)), name.rpartition("/")[0]


def addon_version(location):
    if location.is_dir():
        return ET.parse(location / "addon.xml").getroot().get("version")
    return zip_addon_root(location)[0].get("version")


def addon_platform(root):
    platform = root.findtext("./extension[@point='xbmc.addon.metadata']/platform")
    return platform.strip() if platform else None


@dataclasses.dataclass
class Variant:
    """One per-platform build of an add-on, published in its own
    <id>+<platform>/ folder and reached through a <path> in the catalog."""
    addon_id: str
    platform: str
    version: str
    root: object          # the <addon> element from this build's own addon.xml
    zip_root: str         # name of the top-level folder inside the source zip
    source: pathlib.Path

    @property
    def folder(self):
        return f"{self.addon_id}+{self.platform}"

    @property
    def zip_name(self):
        return f"{self.addon_id}-{self.version}.zip"

    @property
    def rel_path(self):
        """What goes in <path>: relative to the repository's datadir."""
        return f"{self.folder}/{self.zip_name}"


def variant_builds(addon):
    """The newest source/ build per extra platform for this add-on.

    Platform and version are read from each build's own addon.xml, not parsed
    back out of the filename -- platform strings contain hyphens themselves
    ("osx-arm64"), so splitting "pvr.eon+osx-arm64-21.8.4.zip" apart is
    guesswork. The filename only has to be good enough to find candidates.
    """
    if not addon.variants or not SOURCE_DIR.is_dir():
        return []
    newest = {}
    for zip_path in sorted(SOURCE_DIR.glob(f"{addon.id}+*.zip")):
        root, zip_root = zip_addon_root(zip_path)
        platform = addon_platform(root)
        if not platform:
            sys.exit(f"{zip_path.name} declares no <platform>, so Kodi would have "
                     f"no way to tell it apart from this add-on's other builds "
                     f"-- refusing to publish it")
        variant = Variant(addon.id, platform, root.get("version"), root,
                          zip_root, zip_path)
        current = newest.get(platform)
        if current is None or version_key(variant.version) > version_key(current.version):
            newest[platform] = variant
    return [newest[p] for p in sorted(newest)]


# A zip entry carries the mtime of the file it was read from, so a source
# file that is touched but not changed -- an editor writing it back byte for
# byte, or the addon.xml create_repository.py copies into repository.eon/ with
# shutil.copyfile, which does not preserve mtimes -- yields a byte-different
# zip holding identical content. These zips are tracked in git, so each one of
# those lands in the history as a binary change that means nothing, and the
# .md5 beside it changes with it. Rewriting every entry with fixed metadata
# makes a zip's bytes a pure function of its contents: an add-on nobody
# touched produces the file that is already committed, and git sees nothing.
# 1980-01-01 is the zip format's own epoch and the conventional stand-in
# timestamp for a reproducible archive.
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def zip_state(path):
    """(digest, mtime) of an already-published zip, or None if it is new."""
    if not path.is_file():
        return None
    return hashlib.md5(path.read_bytes()).hexdigest(), path.stat().st_mtime


def published_zip_states():
    """Every folder-built zip as it stands before this run, so normalise_zip()
    can tell a rebuild that changed something from one that did not. Taken
    before create_repository.py runs, because that overwrites them."""
    return {path: zip_state(path)
            for addon in ADDONS if not addon.variants_only
            for path in (REPO_ROOT / addon.id).glob(f"{addon.id}-*.zip")}


def normalise_zip(path, previous=None):
    """Rewrite `path` with per-entry timestamps, permissions and ordering
    fixed, so identical contents always give an identical file. Returns
    whether the result differs from what was published before."""
    with zipfile.ZipFile(path) as zf:
        entries = [(info, zf.read(info))
                   for info in sorted(zf.infolist(), key=lambda i: i.filename)]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for info, data in entries:
            clean = zipfile.ZipInfo(info.filename, ZIP_EPOCH)
            clean.compress_type = info.compress_type
            # Unix, so the mode below is what a reader gets back. os.walk order
            # and the umask of whoever ran the publish stay out of the bytes.
            clean.create_system = 3
            if info.is_dir():
                clean.external_attr = (0o40755 << 16) | 0x10
            else:
                clean.external_attr = 0o100644 << 16
            out.writestr(clean, data)
    data = buffer.getvalue()
    path.write_bytes(data)
    write_zip_md5(path)
    if previous and previous[0] == hashlib.md5(data).hexdigest():
        # Byte for byte what was already published. create_repository.py has
        # overwritten the file by now, so the bytes had to be put back, but
        # the mtimes can go back too -- a publish that changed nothing then
        # leaves nothing behind at all, not even a touched timestamp.
        for target in (path, pathlib.Path(f"{path}.md5")):
            os.utime(target, (previous[1], previous[1]))
        return False
    return True


def write_zip_md5(path):
    """Checksum file in create_repository.py generate_checksum()'s layout for
    a binary file: digest, space, '*' marker, basename, UNIX line ending."""
    digest = hashlib.md5(path.read_bytes()).hexdigest()
    with open(f"{path}.md5", "w", newline="\n") as fh:
        fh.write(f"{digest} *{path.name}\n")


def publish_variant(variant):
    """Lay a variant out the way Kodi's own binary add-on repository does:
    <id>+<platform>/<id>-<version>.zip with the metadata files copied in
    beside it -- Kodi resolves an add-on's artwork relative to the folder its
    <path> points into, so the assets cannot be shared between platform
    folders. Returns the published zip's size, for <size>.
    """
    directory = REPO_ROOT / variant.folder
    directory.mkdir(exist_ok=True)
    archive = directory / variant.zip_name
    archive.write_bytes(variant.source.read_bytes())
    write_zip_md5(archive)
    wanted = [(name, name) for name in ("addon.xml",) + OPTIONAL_ASSETS]
    wanted.append(("changelog.txt", f"changelog-{variant.version}.txt"))
    with zipfile.ZipFile(variant.source) as zf:
        for source_name, target_name in wanted:
            try:
                data = zf.read(f"{variant.zip_root}/{source_name}")
            except KeyError:
                continue
            (directory / target_name).write_bytes(data)
    return archive.stat().st_size


def ingest_variant_zips(paths):
    """Archive freshly built extra-platform zips in source/ under the name
    variant_builds() looks for, so a build only has to be handed to
    publish.py once."""
    for raw in paths:
        source = pathlib.Path(raw).expanduser().resolve()
        root, _ = zip_addon_root(source)
        platform = addon_platform(root)
        if not platform:
            sys.exit(f"{source.name} declares no <platform> -- a platform variant "
                     f"needs one so Kodi can tell the builds apart")
        SOURCE_DIR.mkdir(exist_ok=True)
        archived = SOURCE_DIR / f"{root.get('id')}+{platform}-{root.get('version')}.zip"
        if archived.resolve() != source:
            archived.write_bytes(source.read_bytes())
        print(f"source/: archived {archived.name}")


def append_variant_entries(published):
    """Add one <addon> entry per variant to the catalog create_repository.py
    just wrote, before normalise_catalog() re-indents it and recomputes the
    checksum.

    Two entries sharing an id AND a version is deliberate and is how Kodi
    serves binary add-ons itself: <platform> makes Kodi drop the entries that
    do not match the device (it filters them out while parsing addons.xml, so
    the wrong build never reaches the add-on database), and <path> overrides
    the default datadir/<id>/<id>-<version>.zip URL so the surviving entry
    still resolves to its own zip. mirrors.kodi.tv/addons/omega ships
    inputstream.adaptive 21.5.23 six times on exactly this basis.
    """
    if not published:
        return
    path = REPO_ROOT / "addons.xml"
    tree = ET.parse(path)
    for variant, size in published:
        metadata = variant.root.find("./extension[@point='xbmc.addon.metadata']")
        # Appended last, matching the order the official catalog uses.
        ET.SubElement(metadata, "size").text = str(size)
        ET.SubElement(metadata, "path").text = variant.rel_path
        tree.getroot().append(variant.root)
    tree.write(path, encoding="UTF-8", xml_declaration=True)


def prepare_location(addon, args, stack):
    """Resolve an Addon's source to a path safe to hand to
    create_repository.py -- for folders, that means a clean tempdir copy
    with build/VCS cruft stripped, since fetch_addon_from_folder() zips
    everything under the folder with no ignore list of its own."""
    location = addon.locate(args)
    if location.is_dir() and addon.ignore:
        tmp = pathlib.Path(stack.enter_context(tempfile.TemporaryDirectory()))
        dest = tmp / addon.id
        shutil.copytree(location, dest, ignore=shutil.ignore_patterns(*addon.ignore))
        return dest
    return location


def normalise_catalog():
    """Re-indent addons.xml and refresh its checksum.

    create_repository.py appends each add-on's addon.xml verbatim, so the
    catalog inherits whatever indentation each source file used and gets no
    line break between </addon> and the next <addon>. Kodi does not care, but
    anyone reading the file does -- and the checksum has to be recomputed
    afterwards, because that is what devices compare against.
    """
    path = REPO_ROOT / "addons.xml"
    tree = ET.parse(path)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    digest = hashlib.md5(path.read_bytes()).hexdigest()
    # Same layout as create_repository.py's generate_checksum() for a text file.
    with open(REPO_ROOT / "addons.xml.md5", "w", newline="\n") as fh:
        fh.write(f"{digest}  addons.xml\n")
    print(f"addons.xml: re-indented, md5 {digest}")


def prune_zips(directory, addon_id, keep):
    """Delete published files in `directory` beyond the last `keep` versions
    of `addon_id`. Returns the kept versions, newest first."""
    if not directory.is_dir():
        return []
    pattern = re.compile(rf"^{re.escape(addon_id)}-(.+)\.zip$")
    versions = sorted(
        {m.group(1) for f in directory.iterdir() if (m := pattern.match(f.name))},
        key=version_key,
        reverse=True,
    )
    for old in versions[keep:]:
        for name in (f"{addon_id}-{old}.zip", f"{addon_id}-{old}.zip.md5",
                     f"changelog-{old}.txt"):
            (directory / name).unlink(missing_ok=True)
    return versions[:keep]


def prune(addon):
    return prune_zips(REPO_ROOT / addon.id, addon.id, addon.keep)


def prune_variant_source(addon, variants):
    """Drop source/ builds for platforms we still publish, beyond the newest
    `keep` of each -- publish_variant() only ever ships the newest."""
    for variant in variants:
        builds = []
        for f in SOURCE_DIR.glob(f"{addon.id}+{variant.platform}-*.zip"):
            root, _ = zip_addon_root(f)
            if addon_platform(root) == variant.platform:
                builds.append((version_key(root.get("version")), f))
        for _, f in sorted(builds, reverse=True)[addon.keep:]:
            f.unlink()


def rewrite_index(addon_id, kept_versions, folder=None):
    """`folder` differs from `addon_id` for platform builds, whose folder
    carries a +<platform> suffix while the zips inside keep the plain
    <id>-<version>.zip name Kodi builds by default."""
    folder = folder or addon_id
    directory = REPO_ROOT / folder
    lines = [
        "<!DOCTYPE html>", "<html>",
        f"<head><title>Index of /{folder}/</title></head>",
        "<body>", f"<h1>Index of /{folder}/</h1>", "<pre>",
        '<a href="addon.xml">addon.xml</a>',
    ]
    for asset in OPTIONAL_ASSETS:
        if (directory / asset).exists():
            lines.append(f'<a href="{asset}">{asset}</a>')
    for i, v in enumerate(kept_versions):
        tag = "" if i == 0 else " (previous version)"
        changelog = f"changelog-{v}.txt"
        if (directory / changelog).exists():
            lines.append(f'<a href="{changelog}">{changelog}{tag}</a>')
        lines.append(f'<a href="{addon_id}-{v}.zip">{addon_id}-{v}.zip{tag}</a>')
        lines.append(f'<a href="{addon_id}-{v}.zip.md5">{addon_id}-{v}.zip.md5{tag}</a>')
    lines += ["</pre>", "</body>", "</html>", ""]
    (directory / "index.html").write_text("\n".join(lines))


def rewrite_root_index(repo_eon_version):
    """The root listing is what someone bootstrapping a device browses in
    Kodi's "Install from zip file", so repository.eon/ has to be linked here
    like every other add-on: HTTP browsing is pure link-following, and a
    folder GitHub Pages serves perfectly well is invisible to Kodi if nothing
    points at it. The root used to carry a second copy of the repository zip
    instead of that link; the link is the same click and one file fewer to
    keep in step."""
    lines = [
        "<!DOCTYPE html>", "<html>",
        "<head><title>Index of /</title></head>",
        "<body>", "<h1>Index of /</h1>", "<pre>",
        '<a href="addons.xml">addons.xml</a>',
        '<a href="addons.xml.md5">addons.xml.md5</a>',
    ]
    for addon in ADDONS:
        if not addon.variants_only:
            lines.append(f'<a href="{addon.id}/">{addon.id}/</a>')
        # Globbed off disk rather than taken from the variants we just
        # published, so a platform folder still gets listed once its source
        # build has aged out of source/.
        for directory in sorted(REPO_ROOT.glob(f"{addon.id}+*")):
            if directory.is_dir():
                lines.append(f'<a href="{directory.name}/">{directory.name}/</a>')
    lines += ["</pre>", "</body>", "</html>", ""]
    (REPO_ROOT / "index.html").write_text("\n".join(lines))

    # Sweeps up the root copies this script used to make, so a tree published
    # by an older version of it converges on the first run.
    for old in REPO_ROOT.glob("repository.eon-*.zip*"):
        old.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pvr-zip", metavar="ZIP",
                        help="Deprecated alias for --variant-zip, kept because the "
                             "Android build used to be published as pvr.eon's one "
                             "canonical build rather than as a platform variant")
    parser.add_argument("--variant-zip", action="append", default=[], metavar="ZIP",
                        help="Path to a per-platform build of an add-on, e.g. the "
                             "macOS or Android pvr.eon build. Archived in source/ "
                             "and published into its own <id>+<platform>/ folder. "
                             "Repeatable.")
    args = parser.parse_args()

    ingest_variant_zips(args.variant_zip + ([args.pvr_zip] if args.pvr_zip else []))

    previous = published_zip_states()

    with contextlib.ExitStack() as stack:
        locations = [str(prepare_location(a, args, stack))
                     for a in ADDONS if not a.variants_only]
        subprocess.run(
            [sys.executable, "create_repository.py", "--datadir=.", "--no-parallel",
             *locations],
            cwd=REPO_ROOT, check=True,
        )

    # Every zip create_repository.py just built, plus the older versions still
    # kept beside them, so a folder converges the first time this runs. The
    # pvr.eon platform folders are left alone: publish_variant() copies those
    # zips out of source/ byte for byte, so they are already stable, and they
    # are someone else's build artifact to leave intact.
    rebuilt = {}
    for addon in ADDONS:
        if addon.variants_only:
            continue
        rebuilt[addon.id] = sorted(
            archive.name
            for archive in (REPO_ROOT / addon.id).glob(f"{addon.id}-*.zip")
            if normalise_zip(archive, previous.get(archive))
        )

    # Must land after create_repository.py has rewritten addons.xml from
    # scratch, and before normalise_catalog() checksums it.
    published = [(v, publish_variant(v)) for a in ADDONS for v in variant_builds(a)]
    append_variant_entries(published)

    normalise_catalog()

    for addon in ADDONS:
        if not addon.variants_only:
            kept = prune(addon)
            rewrite_index(addon.id, kept)
            changed = rebuilt.get(addon.id) or ["nothing changed"]
            print(f"{addon.id}: kept {kept}, rebuilt {', '.join(changed)}")
        variants = [v for v, _ in published if v.addon_id == addon.id]
        prune_variant_source(addon, variants)
        for variant in variants:
            variant_kept = prune_zips(REPO_ROOT / variant.folder, addon.id, addon.keep)
            rewrite_index(addon.id, variant_kept, folder=variant.folder)
            print(f"{variant.folder}: kept {variant_kept}, catalogued "
                  f"{variant.version} at {variant.rel_path}")

    repo_eon_version = ET.parse(REPO_ROOT / "repository.eon" / "addon.xml").getroot().get("version")
    rewrite_root_index(repo_eon_version)


if __name__ == "__main__":
    main()
