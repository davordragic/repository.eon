"""Gives Kodi's programme guide settings a starting value that suits EON.

Kodi's defaults are one day of guide history and a refresh once the stored
guide is two hours old. Both are wrong here: the first puts the 7 day replay
archive out of reach, and the second means a set-top box re-reads the whole
guide from the provider on nearly every cold start, even though the guide is
sitting in its database already.

A PVR client cannot change these -- the binary add-on API reaches its own
settings and nothing else -- and neither can a skin, which has no builtin for
a system setting. A Python service can, through JSON-RPC, which is why this
add-on exists.

Applied once and then left alone: this is a different default, not a policy.
"""

import json

import xbmc
import xbmcaddon

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo("name")

# epg.pastdaystodisplay is what actually gates replay: Kodi deletes guide
# entries older than this and will not ask the client for them, so a smaller
# number hides the archive no matter what the provider offers.
# epg.epgupdate is the freshness rule for the stored guide, not a download
# schedule -- below it Kodi reads its database, above it it re-reads every
# channel from the client.
SETTINGS = (
    ("epg.pastdaystodisplay", 7),
    ("epg.futuredaystodisplay", 3),
    ("epg.epgupdate", 2880),
)


def log(message, level=xbmc.LOGINFO):
    xbmc.log("{}: {}".format(ADDON_NAME, message), level)


def jsonrpc(method, params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    )))
    if "error" in response:
        raise RuntimeError("{} failed: {}".format(method, response["error"]))
    return response.get("result")


def apply_defaults():
    """Returns a description of what was changed, for the log."""
    changed = []
    for setting, wanted in SETTINGS:
        current = jsonrpc("Settings.GetSettingValue", {"setting": setting})["value"]
        if current == wanted:
            continue
        jsonrpc("Settings.SetSettingValue", {"setting": setting, "value": wanted})
        changed.append("{} {} -> {}".format(setting, current, wanted))
    return changed


def set_applied(value):
    # Only write on a real change: setting an add-on setting raises
    # onSettingsChanged, and writing unconditionally would bounce between
    # here and the monitor forever.
    if ADDON.getSettingBool("applied") != value:
        ADDON.setSettingBool("applied", value)


def run():
    if not ADDON.getSettingBool("enabled"):
        # Clearing the marker is what makes switching this off and back on a
        # way to ask for the recommended values again.
        set_applied(False)
        return

    if ADDON.getSettingBool("applied"):
        return

    try:
        changed = apply_defaults()
    except (RuntimeError, KeyError, ValueError) as error:
        # Leave the marker unset so the next start tries again rather than
        # silently living with Kodi's defaults.
        log("Could not apply the recommended guide settings: {}".format(error),
            xbmc.LOGERROR)
        return

    set_applied(True)
    log("Applied the recommended guide settings: {}".format(
        ", ".join(changed) if changed else "already set, nothing to change"))


class SettingsMonitor(xbmc.Monitor):
    def onSettingsChanged(self):
        run()


if __name__ == "__main__":
    run()
    SettingsMonitor().waitForAbort()
