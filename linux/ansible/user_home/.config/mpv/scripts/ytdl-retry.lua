-- YouTube sometimes answers 403 on the stream URL (seen through a VPN without a
-- PO token), mpv is left with no tracks and closes. Loading the same link again
-- gets fresh stream URLs from yt-dlp, and the second try usually plays.
-- At most two retries per link.
local options = { pattern = "youtu%.?be", max = 2 }
require 'mp.options'.read_options(options, "ytdl-retry")

local tries = {}
local current, failed

mp.register_event("start-file", function()
    current = mp.get_property("path")
    failed = nil
end)

mp.register_event("file-loaded", function()
    if current then tries[current] = nil end
end)

mp.register_event("end-file", function(e)
    if e.reason == "error" and current and current:find(options.pattern) then
        failed = current
    end
end)

mp.add_hook("on_after_end_file", 50, function()
    if not failed then return end
    local path = failed
    failed = nil
    local n = (tries[path] or 0) + 1
    if n > options.max then
        tries[path] = nil
        return
    end
    tries[path] = n
    mp.msg.warn(string.format("load failed, retry %d/%d: %s", n, options.max, path))
    mp.osd_message(string.format("YouTube не отдал поток, пробую ещё раз (%d/%d)", n, options.max), 4)
    -- the retry goes next and the failed entry is dropped, so the playlist
    -- doesn't pile up duplicates
    mp.commandv("loadfile", path, "insert-next")
    mp.commandv("playlist-remove", "current")
end)
