#!/usr/bin/env python3
import http.server
import socketserver
import argparse
import sys
import os
import signal
import json
import html
from pathlib import Path
import zipfile
from urllib.parse import unquote, quote
import re
EXTRA_STEM = re.compile(r"-[0-9a-f]{12}$")

def is_extra_prefix(prefix: str) -> bool:
    leaf = prefix.rstrip("/").rsplit("/", 1)[-1]
    return bool(EXTRA_STEM.search(leaf))

def signal_handler(sig, frame):
    print("\n\nShutting down server… (releasing port)")
    sys.exit(0)

class NoCacheHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, zipfile_obj=None, **kwargs):
        self.zipfile_obj = zipfile_obj
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self):
        if self.zipfile_obj is None:
            return super().do_GET()

        path = unquote(self.path.split("?", 1)[0]).lstrip("/")
        if not path or path.endswith("/"):
            path = "index.html"

        if ".." in path.split("/") or path.startswith("\\"):
            self.send_error(403)
            return

        try:
            data = self.zipfile_obj.read(path)
            if data.startswith(b"\xff\xd8\xff"):
                ctype = "image/jpeg"
            elif data.startswith(b"\x89PNG\r\n\x1a\n"):
                ctype = "image/png"
            elif data.startswith(b"GIF8"):
                ctype = "image/gif"
            else:
                ctype = self.guess_type(path)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except KeyError:
            self.send_error(404)
        except Exception:
            self.send_error(500)


def collect_archives(archive_root: Path):
    zips = {}
    singlefiles = {}
    root = archive_root.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.parent.name in ("backups", "__backups"):
            continue
        if path.name.startswith("backup-"):
            continue
        rel = path.relative_to(root).as_posix()
        if path.suffix.lower() == ".zip":
            prefix = "/" + unquote(rel[:-4].strip("/"))
            zips[prefix] = path
        elif path.name.endswith(".singlefile.html"):
            url = "/" + unquote(rel)
            singlefiles[url] = path
    return zips, singlefiles


def work_id_of(prefix: str) -> str:
    parts = prefix.strip("/").split("/")
    return parts[0] if parts and parts[0] else prefix

def match_zip(mapping, url_path: str):
    path = "/" + url_path.strip("/")
    if path == "/":
        return None, ""
    best = ""
    for prefix in mapping:
        if path == prefix or path.startswith(prefix + "/"):
            if len(prefix) > len(best):
                best = prefix
    if not best:
        return None, ""
    inner = path[len(best):].lstrip("/")
    return mapping[best], inner

def parent_title(prefix: str, zips: dict) -> str | None:
    best = None
    for p in zips:
        if prefix.startswith(p + "/"):
            if best is None or len(p) > len(best):
                best = p
    return best

class ArchiveRootHandler(NoCacheHTTPRequestHandler):
    def __init__(self, *args, zip_mapping=None, singlefile_mapping=None,
                 archive_root=None, layout=None, **kwargs):
        self.zip_mapping = zip_mapping or {}
        self.singlefile_mapping = singlefile_mapping or {}
        self.archive_root = Path(archive_root) if archive_root else None
        self.layout = layout or {
            "gallery-dl": {"output_path": "dump", "leaf_folder": ""},
            "screenshot": {"output_path": "web-archive", "leaf_folder": "screenshot"},
            "wget-text": {"output_path": "web-archive", "leaf_folder": "wget-text", "output_as_zip": True},
            "json-to-html": {"output_path": "web-archive", "leaf_folder": "json-to-html"},
        }
        self._zip_cache = {}
        super().__init__(*args, directory=".", zipfile_obj=None, **kwargs)

    def _zip_for(self, zip_path):
        key = str(zip_path)
        if key not in self._zip_cache:
            self._zip_cache[key] = zipfile.ZipFile(key)
        return self._zip_cache[key]

    def handler_file(self, handler: str, *parts: str) -> Path:
        slot = self.layout.get(handler, {})
        leaf = slot.get("leaf_folder") or ""
        base = self.archive_root / slot.get("output_path", "web-archive")
        if leaf:
            return base.joinpath(*parts[:-1], leaf, parts[-1]) if parts else base / leaf
        return base.joinpath(*parts)

    def _twitter_json_section(self) -> str:
        if self.archive_root is None:
            return ""
        dump_name = self.layout.get("gallery-dl", {}).get("output_path", "dump")
        dump_root = self.archive_root / dump_name
        if not dump_root.is_dir():
            return ""
        rows = []
        for path in sorted(dump_root.rglob("*.json")):
            if path.parent.name in ("backups", "__backups") or path.name.startswith("backup-"):
                continue
            href = "/" + path.relative_to(self.archive_root).as_posix()
            user_id = path.parent.parent.name
            tweet_id = path.parent.name
            name, title = user_id, tweet_id
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                author = data.get("author") or data.get("user") or {}
                name = author.get("name") or author.get("screen_name") or name
                title = data.get("content") or data.get("full_text") or data.get("text") or title
                title = " ".join(str(title).split())
                if len(title) > 120:
                    title = title[:117] + "..."
            except Exception:
                pass
            shot = self.handler_file("screenshot", user_id, tweet_id, "screenshot.png")
            shot_href = "/" + shot.relative_to(self.archive_root).as_posix()
            if shot.is_file():
                shot_a = f'<a class="sf" href="{quote(shot_href)}">(screenshot)</a>'
            else:
                shot_a = '<span class="missing">screenshot</span>'
            thread = self.handler_file("json-to-html", user_id, tweet_id, "reconstructed-twitter-thread.html")
            thread_href = "/" + thread.relative_to(self.archive_root).as_posix()
            if thread.is_file():
                thread_a = f'<a class="wget" href="{quote(thread_href)}">(thread)</a>'
            else:
                thread_a = ""
            text_slot = self.layout.get("wget-text", {})
            if text_slot.get("output_as_zip", True):
                text_target = self.handler_file("wget-text", user_id, tweet_id, f"{tweet_id}.zip")
            else:
                text_target = self.handler_file("wget-text", user_id, tweet_id, "SUCCESSFUL_DOWNLOAD")
            if text_target.is_file():
                text_href = "/" + text_target.relative_to(self.archive_root).as_posix()
                text_a = f'<a class="sf" href="{quote(text_href)}">(text)</a>'
            else:
                text_a = ""
            links = " · ".join(part for part in (f'<a class="wget" href="{quote(href)}">(json)</a>', shot_a, thread_a, text_a) if part)
            rows.append(
                f'<div class="work"><div class="work-id">{html.escape(str(name))}</div>'
                f'<div class="title">{html.escape(title)} {links}</div></div>'
            )
        if not rows:
            return ""
        return "<h1>Twitter JSON</h1>\n" + "\n".join(rows)

    def do_GET(self):
        raw = unquote(self.path.split("?", 1)[0])
        path_norm = "/" + raw.strip("/")

        if path_norm in self.zip_mapping and not raw.endswith("/"):
            self.send_response(301)
            self.send_header("Location", path_norm + "/")
            self.end_headers()
            return

        if path_norm in self.singlefile_mapping:
            html_path = self.singlefile_mapping[path_norm]
            data = html_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if self.archive_root is not None and ".." not in raw.split("/"):
            rel = raw.lstrip("/")
            parts = rel.split("/")
            serve_file = rel.startswith(f"{self.layout.get('gallery-dl', {}).get('output_path', 'dump')}/") or rel.endswith("screenshot.png") or rel.endswith("reconstructed-twitter-thread.html") or rel.endswith(".singlefile.html") or "/wget-text/" in rel or rel.endswith(".zip")
            if serve_file and "__backups" not in parts and "backups" not in parts:
                candidate = (self.archive_root / rel).resolve()
                root = self.archive_root.resolve()
                if candidate.is_file() and (root == candidate or root in candidate.parents):
                    data = candidate.read_bytes()
                    if candidate.name == "screenshot.png" or data.startswith(b"\x89PNG\r\n\x1a\n"):
                        ctype = "image/png"
                    elif candidate.suffix.lower() == ".json":
                        ctype = "application/json; charset=utf-8"
                    elif candidate.suffix.lower() in (".html", ".htm"):
                        ctype = "text/html; charset=utf-8"
                    else:
                        ctype = self.guess_type(candidate.name)
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return

        zip_path, inner = match_zip(self.zip_mapping, raw)

        if raw in ("", "/"):
            works = {}

            def add_prefix(prefix, has_zip=False):
                if is_extra_prefix(prefix):
                    parent = prefix.rsplit("/", 1)[0] or prefix
                    slot = works.setdefault(parent, {"id_zip": None, "extras": []})
                    if prefix not in slot["extras"]:
                        slot["extras"].append(prefix)
                else:
                    slot = works.setdefault(prefix, {"id_zip": None, "extras": []})
                    if has_zip:
                        slot["id_zip"] = prefix

            for prefix in self.zip_mapping:
                add_prefix(prefix, has_zip=True)
            for url in self.singlefile_mapping:
                stem = (
                    url[: -len(".singlefile.html")]
                    if url.endswith(".singlefile.html")
                    else url
                )
                add_prefix(stem, has_zip=False)

            def sf_url(prefix):
                return prefix + ".singlefile.html"

            rows = []
            for work in sorted(works):
                info = works[work]
                title = info.get("id_zip")
                extras = info.get("extras") or []
                rows.append(f'<div class="work"><div class="work-id">{work.lstrip("/")}</div>')
                if title:
                    wget = f'<a class="wget" href="{title}/">(wget)</a>'
                    sf = sf_url(title)
                    if sf in self.singlefile_mapping:
                        sf_a = f'<a class="sf" href="{sf}">(singlefile)</a>'
                    else:
                        sf_a = '<span class="missing">singlefile</span>'
                    rows.append(f'<div class="title">id {wget} · {sf_a}</div>')
                else:
                    rows.append('<div class="title"><span class="missing">id (no wget)</span></div>')
                for extra in sorted(extras):
                    wget = f'<a class="wget" href="{extra}/">(wget)</a>'
                    sf = sf_url(extra)
                    if sf in self.singlefile_mapping:
                        sf_a = f'<a class="sf" href="{sf}">(singlefile)</a>'
                    else:
                        sf_a = '<span class="missing">singlefile</span>'
                    leaf = extra[len(work):].lstrip("/") if extra.startswith(work) else extra.lstrip("/")
                    rows.append(
                        f'<div class="extra"><i>extra</i> {leaf} {wget} · {sf_a}</div>'
                    )
                rows.append("</div>")

            body = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Archive</title>
<style>
body{font-family:sans-serif;margin:1.5rem;background:#f6f4ef;color:#222}
h1{font-size:1.3rem}
.work{margin:1.2rem 0;padding:.6rem .8rem;background:#fff;border-left:4px solid #3d5a3d}
.work-id{font-weight:700;margin-bottom:.35rem}
.title{color:#1a4d2e}
.extra{margin:.2rem 0 .2rem 1.4rem;color:#333;font-size:.95rem}
a.wget{color:#0b57d0;margin-right:.4rem}
a.sf{color:#7a2ea0}
.missing{color:#999}
</style></head><body><h1>Archive</h1>
""" + "\n".join(rows) + self._twitter_json_section() + "</body></html>"
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if zip_path is None:
            self.send_error(404)
            return

        zip_path_display=os.path.basename(zip_path)
        print(f"Reading from zip file: {zip_path_display}")
        self.zipfile_obj = self._zip_for(zip_path)
        if not inner or inner.endswith("/"):
            self.path = "/index.html"
        else:
            self.path = "/" + inner
        return NoCacheHTTPRequestHandler.do_GET(self)

def load_layout(configuration_file):
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

def main():
    parser = argparse.ArgumentParser(description="Simple no-cache Python HTTP server")
    parser.add_argument("-d", "--directory", default=".",
                        help="Directory to serve (default: current)")
    parser.add_argument("-p", "--port", type=int, default=8000,
                        help="Port to listen on (default: 8000)")
    parser.add_argument("-H", "--host", default="127.0.0.1",
                        help="Host to bind to (use 127.0.0.1 for network access)")
    parser.add_argument("--archive-root", default=None)
    parser.add_argument("--configuration-file", default=None)

    args = parser.parse_args()
    signal.signal(signal.SIGINT, signal_handler)
    socketserver.TCPServer.allow_reuse_address = True
    layout = load_layout(args.configuration_file)

    if args.archive_root:
        root = Path(args.archive_root).resolve()
        if not root.is_dir():
            print(f"Error: '{root}' is not a directory.")
            sys.exit(1)
        zips, singlefiles = collect_archives(root)
        handler = lambda *a, **kw: ArchiveRootHandler(
            *a,
            zip_mapping=zips,
            singlefile_mapping=singlefiles,
            archive_root=root,
            layout=layout,
            **kw,
        )
        dump_name = layout.get("gallery-dl", {}).get("output_path", "dump")
        web_name = layout.get("screenshot", {}).get("output_path", "web-archive")
        twitter_json = len(list((root / dump_name).rglob("*.json"))) if (root / dump_name).is_dir() else 0
        screenshots = len(list((root / web_name).rglob("screenshot.png"))) if (root / web_name).is_dir() else 0
        serving = f"archive root ({len(zips)} zips, {len(singlefiles)} singlefile, {twitter_json} twitter json, {screenshots} screenshots)"
        directory_path = root
    else:
        directory_path = Path(args.directory).resolve()
        if not directory_path.exists():
            print(f"Error: Directory '{args.directory}' does not exist.")
            sys.exit(1)
        if directory_path.is_file() and directory_path.suffix.lower() == ".zip":
            try:
                zf = zipfile.ZipFile(str(directory_path))
            except zipfile.BadZipFile:
                print(f"Error: '{args.directory}' is not a valid zip file.")
                sys.exit(1)
            is_zip_mode = True
        else:
            if not directory_path.is_dir():
                print(f"Error: '{args.directory}' is not a directory or zip file.")
                sys.exit(1)
            zf = None
            is_zip_mode = False
            os.chdir(directory_path)
        handler = lambda *a, **kw: NoCacheHTTPRequestHandler(
            *a,
            directory=str(directory_path) if not is_zip_mode else None,
            zipfile_obj=zf,
            **kw,
        )
        serving = "zip file" if is_zip_mode else "directory"

    httpd = None
    try:
        httpd = socketserver.TCPServer((args.host, args.port), handler)
        print(f"Serving {serving}:\t{directory_path}")
        print(f"URL              :\thttp://{args.host}:{args.port}")
        print("\nPress Ctrl+C to stop\n")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down gracefully")
    except OSError as e:
        if e.errno == 98:
            print(f"Error: port {args.port} is already in use.")
            print("Tip: wait a few seconds or use a different port.")
        else:
            print(f"Error: {e}")
    finally:
        if httpd:
            try:
                httpd.server_close()
                print("Port is released successfully.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
