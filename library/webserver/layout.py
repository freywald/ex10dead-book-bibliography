# webserver: overview layout is unchanged. Only the file locations move.
# Load configuration.yaml the same way as the archiver (expand -t 4, then YAML).

def load_layout(configuration_file: str | None) -> dict:
    layout = {
        "gallery-dl": {"output_path": "dump", "leaf_folder": ""},
        "screenshot": {"output_path": "web-archive", "leaf_folder": "screenshot"},
        "wget": {"output_path": "web-archive", "leaf_folder": "wget"},
        "wget-text": {"output_path": "web-archive", "leaf_folder": "wget-text", "output_as_zip": True},
        "singlefile": {"output_path": "web-archive", "leaf_folder": "singlefile"},
        "json-to-html": {"output_path": "web-archive", "leaf_folder": "json-to-html"},
    }
    if not configuration_file:
        return layout
    import subprocess
    raw = subprocess.check_output(["expand", "-t", "4", configuration_file])
    parsed = subprocess.check_output(["yq", "--output-format=json"], input=raw)
    data = json.loads(parsed)
    for name, item in (data.get("handlers") or {}).items():
        slot = layout.setdefault(name, {})
        if "output_path" in item:
            slot["output_path"] = item["output_path"]
        if "leaf_folder" in item:
            slot["leaf_folder"] = item["leaf_folder"]
        if "output_as_zip" in item:
            slot["output_as_zip"] = item["output_as_zip"]
    return layout

def handler_file(archive_root: Path, layout: dict, handler: str, *parts: str) -> Path:
    slot = layout[handler]
    leaf = slot.get("leaf_folder") or ""
    base = archive_root / slot["output_path"]
    if leaf:
        return base.joinpath(*parts[:-1], leaf, parts[-1]) if parts else base / leaf
    return base.joinpath(*parts)

# Twitter section, same rows, new hrefs:
#   json:     handler_file(root, layout, "gallery-dl", user_id, tweet_id, f"{tweet_id}.json")
#   screenshot: handler_file(root, layout, "screenshot", user_id, tweet_id, "screenshot.png")
#   thread:   handler_file(root, layout, "json-to-html", user_id, tweet_id, "reconstructed-twitter-thread.html")
#   text:     a zip under the wget-text leaf when output_as_zip, else the SUCCESSFUL_DOWNLOAD directory
#
# collect_archives already finds any .zip and .singlefile.html by rglob, so the
# overview links keep working once the href is the zip path without .zip, which
# now includes the leaf segment: /web-archive/$id/wget/$stem
