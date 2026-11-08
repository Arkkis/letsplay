"""YouTube MCP server for the let's play channel: everything after the user uploads a video in YouTube Studio.

Uploading stays manual: API uploads from an unaudited Google Cloud project are locked to private.
  youtube_mcp.py auth   one-time browser sign-in (stores a refresh token)
  youtube_mcp.py        run the MCP server over stdio
Credentials live in ~/.config/letsplay-youtube/: client_secret.json (Desktop-app OAuth client) and token.json.
"""
import glob, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import CFG, out_dir
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.expanduser("~/.config/letsplay-youtube")
SECRET, TOKEN = f"{CONF}/client_secret.json", f"{CONF}/token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl",  # force-ssl: captions
          "https://www.googleapis.com/auth/yt-analytics.readonly"]  # audience retention
GAMING = "20"


def auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    creds = InstalledAppFlow.from_client_secrets_file(SECRET, SCOPES).run_local_server(port=0)
    os.makedirs(CONF, exist_ok=True)
    with open(os.open(TOKEN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
        fh.write(creds.to_json())
    print("signed in; token saved to", TOKEN)


def credentials():
    if not os.path.exists(TOKEN):
        raise RuntimeError(f"not signed in: run `{sys.executable} {__file__} auth`")
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        with open(TOKEN, "w") as fh:
            fh.write(creds.to_json())
    return creds


def yt():
    return build("youtube", "v3", credentials=credentials(), cache_discovery=False)


def retention(video_id):
    """Audience retention curve: [(position 0–1, share still watching, relative performance), ...] (100 points);
    [] when YouTube has no data yet. Needs the analytics scope: a token from before it exists must be renewed with `auth`."""
    from googleapiclient.errors import HttpError
    an = build("youtubeAnalytics", "v2", credentials=credentials(), cache_discovery=False)
    try:
        r = an.reports().query(ids="channel==MINE", startDate="2000-01-01", endDate=time.strftime("%Y-%m-%d"), dimensions="elapsedVideoTimeRatio",
                               metrics="audienceWatchRatio,relativeRetentionPerformance", filters=f"video=={video_id}").execute()
    except HttpError as e:
        if e.resp.status == 403 and b"accessNotConfigured" in e.content:
            raise RuntimeError("YouTube Analytics API is not enabled in the Google Cloud project: enable youtubeanalytics.googleapis.com") from e
        if e.resp.status == 403:
            raise RuntimeError(f"analytics not allowed by the saved sign-in: run `{sys.executable} {__file__} auth` again") from e
        raise
    return [(row[0], row[1], row[2]) for row in r.get("rows", [])]


def out_file(output, ext):
    edl = episode_edl(output)
    folder = os.path.join(ROOT, out_dir(edl)) if edl else None
    path = folder and os.path.join(folder, f"{output}{ext}")
    if not path or os.path.dirname(os.path.realpath(path)) != os.path.realpath(folder) or not os.path.exists(path):
        raise ValueError(f"no such episode file: {output}{ext} (out/<playlist>/, from the edit whose output is {output!r})")
    return path


def update_snippet(y, video_id, **changes):
    """videos.update replaces the whole snippet, so merge the changes into the current one."""
    v = y.videos().list(part="snippet", id=video_id).execute()["items"]
    if not v:
        raise ValueError(f"video {video_id} not found on this channel")
    s = v[0]["snippet"]
    snippet = {k: s[k] for k in ("title", "description", "categoryId", "tags", "defaultLanguage", "defaultAudioLanguage") if k in s}
    snippet.update({k: v for k, v in changes.items() if v is not None})
    y.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
    return snippet


STATUS_FIELDS = ("privacyStatus", "publishAt", "license", "embeddable", "publicStatsViewable", "selfDeclaredMadeForKids", "containsSyntheticMedia")


def update_status(y, video_id, **changes):
    """videos.update replaces the whole status, so merge the changes into the current writable fields."""
    cur = y.videos().list(part="status", id=video_id).execute()["items"][0]["status"]
    status = {k: cur[k] for k in STATUS_FIELDS if k in cur}
    status.setdefault("selfDeclaredMadeForKids", cur.get("madeForKids", False))
    status.update(changes)
    if status.get("publishAt") and status["privacyStatus"] != "private":
        status.pop("publishAt")
    y.videos().update(part="status", body={"id": video_id, "status": status}).execute()
    return status


def episode_edl(output):
    return next((e for e in map(lambda f: json.load(open(f)), glob.glob(f"{ROOT}/edits/*.json")) if e.get("output") == output), None)


def set_captions(y, video_id, path, language, name):
    """Upload a subtitle track, replacing this channel's existing track in the same language."""
    media = MediaFileUpload(path, mimetype="application/octet-stream")
    old = [c for c in y.captions().list(part="snippet", videoId=video_id).execute()["items"]
           if c["snippet"]["language"] == language and c["snippet"].get("trackKind") != "asr"]
    if old:
        y.captions().update(part="snippet", body={"id": old[0]["id"], "snippet": {"isDraft": False}}, media_body=media).execute()
    else:
        y.captions().insert(part="snippet", body={"snippet": {"videoId": video_id, "language": language, "name": name, "isDraft": False}},
                            media_body=media).execute()


if __name__ == "__main__" and sys.argv[1:] == ["auth"]:
    auth()
    sys.exit()

from mcp.server.mcpserver import MCPServer

server = MCPServer("youtube", instructions="Manage the user's YouTube let's play videos after they upload them in Studio. "
                   "Never change visibility or schedule publishing without the user's explicit go for that video.")


@server.tool()
def list_videos(limit: int = 10) -> list[dict]:
    """The channel's most recent uploads (including private and drafts) with id, title, visibility, schedule and stats."""
    y = yt()
    uploads = y.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids = [i["contentDetails"]["videoId"] for i in
           y.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=min(limit, 50)).execute()["items"]]
    if not ids:
        return []
    vids = y.videos().list(part="snippet,status,statistics,contentDetails", id=",".join(ids)).execute()["items"]
    return [{"id": v["id"], "title": v["snippet"]["title"], "privacy": v["status"]["privacyStatus"],
             "publishAt": v["status"].get("publishAt"), "duration": v["contentDetails"]["duration"],
             "views": v["statistics"].get("viewCount"), "likes": v["statistics"].get("likeCount"),
             "comments": v["statistics"].get("commentCount")} for v in vids]


@server.tool()
def apply_episode(video_id: str, output: str, tags: list[str] | None = None) -> dict:
    """Fill an uploaded video from a rendered episode in out/<playlist>/: title = `output`, description (with chapters and credits),
    thumbnail, subtitles (<output>.<language>.srt), translated title/description (<output>.<translation>.json),
    category Gaming, the channel's language, recording date (from the VOD date), not made for kids, no altered content.
    Visibility is untouched. Languages come from config.json."""
    lang, tr = CFG["language"], CFG.get("translation")
    y = yt()
    edl = episode_edl(output) or {}
    description = open(out_file(output, ".description.txt")).read().strip()
    snippet = update_snippet(y, video_id, title=(edl.get("youtubeTitle") or output)[:100], description=description, categoryId=GAMING, tags=tags,
                             defaultLanguage=lang, defaultAudioLanguage=lang)
    done = ["title", "description", "tags", "category", "language"]
    y.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(out_file(output, ".jpg"), mimetype="image/jpeg")).execute()
    done.append("thumbnail")
    update_status(y, video_id, selfDeclaredMadeForKids=False, containsSyntheticMedia=False, license="youtube",
                  embeddable=True, publicStatsViewable=True)
    done.append("not for kids / no altered content")
    date = edl and re.search(r"(\d{4}-\d{2}-\d{2})$", edl["vod"])
    if date:
        y.videos().update(part="recordingDetails", body={"id": video_id, "recordingDetails": {"recordingDate": f"{date[1]}T00:00:00Z"}}).execute()
        done.append(f"recorded {date[1]}")
    try:
        if not tr:
            raise ValueError("no translation language configured")
        t = json.load(open(out_file(output, f".{tr}.json")))
        t_title = (edl.get(tr) or {}).get("youtubeTitle") or t["title"]
        y.videos().update(part="localizations", body={"id": video_id, "localizations": {tr: {"title": t_title[:100], "description": t["description"]}}}).execute()
        done.append(f"{tr} title/description")
    except ValueError:
        pass  # episode has no English translation
    try:
        if not CFG.get("subtitles", True):
            raise ValueError("subtitles off in config")
        set_captions(y, video_id, out_file(output, f".{lang}.srt"), lang, CFG.get("subtitle_name", lang))
        done.append(f"{lang} subtitles")
    except ValueError:
        pass  # no subtitle file
    return {"id": video_id, "title": snippet["title"], "applied": done}


@server.tool()
def update_video(video_id: str, title: str | None = None, description: str | None = None, tags: list[str] | None = None) -> dict:
    """Change a video's title, description or tags; omitted fields keep their current value."""
    s = update_snippet(yt(), video_id, title=title, description=description, tags=tags)
    return {"id": video_id, "title": s["title"], "tags": s.get("tags", [])}


@server.tool()
def set_thumbnail(video_id: str, output: str) -> str:
    """Set the thumbnail from out/<playlist>/<output>.jpg (max 2 MB)."""
    yt().thumbnails().set(videoId=video_id, media_body=MediaFileUpload(out_file(output, ".jpg"), mimetype="image/jpeg")).execute()
    return f"thumbnail set from {os.path.relpath(out_file(output, '.jpg'), ROOT)}"


@server.tool()
def add_to_playlist(video_id: str, playlist: str) -> str:
    """Append the video to the playlist with this exact title, creating it (public) if missing. No-op if already in it."""
    y = yt()
    mine = y.playlists().list(part="snippet", mine=True, maxResults=50).execute()["items"]
    pl = next((p["id"] for p in mine if p["snippet"]["title"] == playlist), None)
    items = []
    if pl:
        items = y.playlistItems().list(part="contentDetails", playlistId=pl, maxResults=50).execute()["items"]
    else:  # a new playlist can't be listed for a while, and is empty anyway
        pl = y.playlists().insert(part="snippet,status", body={"snippet": {"title": playlist, "defaultLanguage": CFG["language"]},
                                                                "status": {"privacyStatus": "public"}}).execute()["id"]
    if any(i["contentDetails"]["videoId"] == video_id for i in items):
        return f"already in '{playlist}'"
    for attempt in range(5):  # a just-created playlist answers 409 SERVICE_UNAVAILABLE for a while
        try:
            y.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": pl, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
            return f"added to '{playlist}' ({pl})"
        except HttpError as e:
            if e.resp.status != 409 or attempt == 4:
                raise
            time.sleep(15 * (attempt + 1))


@server.tool()
def set_visibility(video_id: str, privacy: str, publish_at: str | None = None) -> dict:
    """Publish: privacy is private | unlisted | public. With publish_at (ISO 8601, e.g. 2026-11-01T16:00:00+02:00) the video
    stays private and goes public at that time. Only call after the user explicitly approved publishing this video."""
    if privacy not in ("private", "unlisted", "public"):
        raise ValueError("privacy must be private, unlisted or public")
    status = update_status(yt(), video_id, **({"privacyStatus": "private", "publishAt": publish_at} if publish_at else {"privacyStatus": privacy}))
    return {"id": video_id, **status}


@server.tool()
def video_retention(video_id: str) -> list[dict]:
    """Audience retention of a published video in 5 % steps: position (0–1), share of viewers still watching, performance
    relative to similar videos. Empty until YouTube has a few days of views. `lp.py retention <edl>` maps it onto the script."""
    return [{"position": p, "watching": w, "relative": r} for p, w, r in retention(video_id) if round(p * 100) % 5 == 0]


if __name__ == "__main__":
    server.run()
