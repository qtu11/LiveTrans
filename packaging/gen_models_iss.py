"""Sinh danh sách model cho bộ cài Inno Setup (URL ghim commit + SHA256 + dung lượng, theo chế độ chất lượng).

Chạy: python packaging/gen_models_iss.py → packaging/build/models_files.iss, models_code.iss, models_defs.iss
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from livetrans.models import MT_MODELS, NLLB_FILES, PROFILES, whisper_repo  # noqa: E402
from livetrans.tts import VOICE_FILES, VOICE_REPO  # noqa: E402

OUT = ROOT / "packaging" / "build"
WHISPER_FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "vocabulary.json"]
LETTER = {"fast": "f", "balanced": "b", "accurate": "a"}  # khớp với ProfileLetter() trong LiveTrans.iss


def repo_files(repo: str, wanted: list[str]) -> tuple[str, list[dict]]:
    """File cần tải trong repo; tên không có ``/`` được coi là model CT2 (bắt buộc config.json + model.bin),
    tên có đường dẫn (giọng Piper) thì bắt buộc đủ tất cả."""
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{repo}?blobs=true", timeout=30) as r:
        info = json.load(r)
    files = []
    for s in info["siblings"]:
        if s["rfilename"] in wanted:
            lfs = s.get("lfs") or {}
            files.append({"name": s["rfilename"], "size": s.get("size") or lfs.get("size") or 0,
                          "sha256": lfs.get("sha256", "")})
    required = set(wanted) if all("/" in w for w in wanted) else {"config.json", "model.bin"}
    missing = required - {f["name"] for f in files}
    if missing:
        raise SystemExit(f"{repo}: thiếu {sorted(missing)}")
    return info["sha"], files


def targets() -> list[tuple[str, str, list[str], str]]:
    """(repo, thư mục trong models/, file, chuỗi chế độ dùng model này)."""
    usage: dict[tuple[str, str], set[str]] = {}
    for p in PROFILES.values():
        for size in {p.whisper, p.preview}:
            usage.setdefault(("whisper", size), set()).add(LETTER[p.key])
        usage.setdefault(("mt", p.mt), set()).add(LETTER[p.key])
    out = []
    for (kind, key), letters in sorted(usage.items()):
        mask = "".join(sorted(letters))
        if kind == "whisper":
            out.append((whisper_repo(key), f"whisper-{key}", WHISPER_FILES, mask))
        else:
            spec = MT_MODELS[key]
            out.append((spec.repo, spec.folder, NLLB_FILES, mask))
    # Giọng đọc tiếng Việt (Piper) — mọi chế độ; file nằm trong thư mục con của repo
    out.append((VOICE_REPO, "piper", VOICE_FILES, "".join(sorted(LETTER.values()))))
    return out


def main() -> None:
    files_lines, code_lines = [], []
    profile_bytes = {k: 0 for k in PROFILES}
    for repo, folder, wanted, mask in targets():
        sha, files = repo_files(repo, wanted)
        size = 0
        for f in files:
            sub, _, base = f["name"].rpartition("/")
            dest_dir = "\\".join(p for p in [folder, sub.replace("/", "\\")] if p)
            tmp_name = f"{folder}__{f['name'].replace('/', '__')}"
            url = f"https://huggingface.co/{repo}/resolve/{sha}/{f['name']}"
            files_lines.append(
                f'Source: "{{tmp}}\\{tmp_name}"; DestDir: "{{app}}\\models\\{dest_dir}"; DestName: "{base}"; '
                "Flags: external skipifsourcedoesntexist ignoreversion"
            )
            code_lines.append(
                f"  AddModelFile('{url}', '{tmp_name}', '{dest_dir}\\{base}', '{f['sha256']}', '{mask}');"
            )
            size += f["size"]
        for key, letter in LETTER.items():
            if letter in mask:
                profile_bytes[key] += size
        print(f"{folder:40} {size / 1e6:8.1f} MB  [{mask}]")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "models_files.iss").write_text("\n".join(files_lines) + "\n", encoding="utf-8-sig")
    (OUT / "models_code.iss").write_text(
        "procedure AddAllModelFiles;\nbegin\n" + "\n".join(code_lines) + "\nend;\n", encoding="utf-8-sig"
    )
    defs = [f"#define ModelsBytes {max(profile_bytes.values())}"]
    for key, b in profile_bytes.items():
        gb = f"{b / 1e9:.1f}".replace(".", ",")
        defs.append(f'#define Size_{key} "{gb}"')
        print(f"chế độ {key}: {gb} GB")
    (OUT / "models_defs.iss").write_text("\n".join(defs) + "\n", encoding="utf-8-sig")


if __name__ == "__main__":
    main()
