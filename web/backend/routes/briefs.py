import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_briefs_dir
from ..markdown_render import render_markdown
from ..models import BriefResponse, BriefIndexResponse, BriefIndexEntry

router = APIRouter(tags=["briefs"])


def _find_brief_file(briefs_dir: str, slug: str) -> str | None:
    """Look for a brief file by slug, searching subdirectories."""
    # Direct path
    direct = os.path.join(briefs_dir, f"{slug}.md")
    if os.path.isfile(direct):
        return direct
    # Shift directory index
    shift_index = os.path.join(briefs_dir, slug, "_index.md")
    if os.path.isfile(shift_index):
        return shift_index
    # Search subdirectories
    for entry in os.listdir(briefs_dir):
        sub = os.path.join(briefs_dir, entry)
        if os.path.isdir(sub):
            candidate = os.path.join(sub, f"{slug}.md")
            if os.path.isfile(candidate):
                return candidate
    return None


def _find_json_file(briefs_dir: str, slug: str) -> str | None:
    """Look for a JSON sidecar by slug, searching subdirectories."""
    direct = os.path.join(briefs_dir, f"{slug}.json")
    if os.path.isfile(direct):
        return direct
    for entry in os.listdir(briefs_dir):
        sub = os.path.join(briefs_dir, entry)
        if os.path.isdir(sub):
            candidate = os.path.join(sub, f"{slug}.json")
            if os.path.isfile(candidate):
                return candidate
    return None


@router.get("/api/briefs/{slug}")
async def get_brief(
    slug: str,
    briefs_dir: str = Depends(get_briefs_dir),
):
    md_path = _find_brief_file(briefs_dir, slug)
    if md_path is None:
        raise HTTPException(status_code=404, detail="Brief not found")

    with open(md_path) as f:
        md_content = f.read()

    sidecar = None
    source = "markdown-only"
    json_path = _find_json_file(briefs_dir, slug)
    if json_path:
        try:
            with open(json_path) as f:
                raw = json.load(f)
            from ..models import BriefSidecar
            sidecar = BriefSidecar(**raw)
            source = "sidecar"
        except (json.JSONDecodeError, Exception):
            pass

    return BriefResponse(slug=slug, prose_md=md_content, sidecar=sidecar, source=source)


@router.get("/api/briefs")
async def list_briefs(
    shift: str = Query(default=""),
    briefs_dir: str = Depends(get_briefs_dir),
):
    if shift:
        index_path = os.path.join(briefs_dir, shift, "_index.md")
        if not os.path.isfile(index_path):
            raise HTTPException(status_code=404, detail="Shift index not found")
        with open(index_path) as f:
            md_content = f.read()

        index_html = render_markdown(md_content)

        shift_dir = os.path.join(briefs_dir, shift)
        run_files = sorted(
            f[:-3] for f in os.listdir(shift_dir)
            if f.endswith(".md") and f != "_index.md"
        )
        entries: list[BriefIndexEntry] = []
        for slug in run_files:
            run_path = os.path.join(shift_dir, f"{slug}.md")
            if not os.path.isfile(run_path):
                continue
            with open(run_path) as f:
                first_line = f.readline().strip().lstrip("#").strip()
            entries.append(BriefIndexEntry(
                slug=slug,
                title=first_line,
                scheduled="",
                summary_line="",
            ))
        return BriefIndexResponse(index_md_html=index_html, runs=entries)

    files: list[str] = []
    for entry in sorted(os.listdir(briefs_dir)):
        fpath = os.path.join(briefs_dir, entry)
        if entry.endswith(".md") and entry != "_index.md" and os.path.isfile(fpath):
            files.append(entry[:-3])
    return {"briefs": files}
