import os
import json
import uuid
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from cryptography.fernet import Fernet, InvalidToken
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
BLOCKS_DIR = STORAGE_DIR / "blocks"
MANIFESTS_DIR = STORAGE_DIR / "manifests"
KEY_FILE = BASE_DIR / "secret.key"
BLOCK_SIZE = 1024 * 1024  # 1 MB blocks

for folder in (BLOCKS_DIR, MANIFESTS_DIR):
    folder.mkdir(parents=True, exist_ok=True)

# For a college demonstration only. In a real system, store keys in a managed
# key service and do not keep them beside the encrypted files.
if not KEY_FILE.exists():
    KEY_FILE.write_bytes(Fernet.generate_key())
cipher = Fernet(KEY_FILE.read_bytes())

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-for-local-demo")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit


@app.get("/")
def index():
    items = []
    for manifest_path in sorted(MANIFESTS_DIR.glob("*.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            items.append({
                "id": manifest["id"],
                "filename": manifest["filename"],
                "blocks": manifest["blocks"],
                "size": manifest["size"],
            })
        except (OSError, json.JSONDecodeError, KeyError):
            continue
    return render_template("index.html", items=items)


@app.post("/upload")
def upload():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        flash("Please choose a file first.", "error")
        return redirect(url_for("index"))

    original_name = secure_filename(uploaded.filename)
    if not original_name:
        flash("That filename is not supported. Please rename the file and try again.", "error")
        return redirect(url_for("index"))

    file_id = uuid.uuid4().hex
    total_size = 0
    block_count = 0
    block_names = []

    try:
        while True:
            chunk = uploaded.stream.read(BLOCK_SIZE)
            if not chunk:
                break
            encrypted = cipher.encrypt(chunk)
            block_name = f"{file_id}_{block_count:05d}.bin"
            (BLOCKS_DIR / block_name).write_bytes(encrypted)
            block_names.append(block_name)
            total_size += len(chunk)
            block_count += 1

        if block_count == 0:
            flash("The selected file is empty.", "error")
            return redirect(url_for("index"))

        manifest = {
            "id": file_id,
            "filename": original_name,
            "size": total_size,
            "blocks": block_count,
            "block_files": block_names,
        }
        (MANIFESTS_DIR / f"{file_id}.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        flash(f"Upload successful! File encrypted and stored in {block_count} block(s).", "success")
    except Exception:
        # Remove partial output if something goes wrong.
        for name in block_names:
            (BLOCKS_DIR / name).unlink(missing_ok=True)
        (MANIFESTS_DIR / f"{file_id}.json").unlink(missing_ok=True)
        flash("Upload failed. Please try again.", "error")

    return redirect(url_for("index"))


@app.get("/download/<file_id>")
def download(file_id):
    if not file_id.isalnum():
        flash("Invalid file ID.", "error")
        return redirect(url_for("index"))

    manifest_path = MANIFESTS_DIR / f"{file_id}.json"
    if not manifest_path.exists():
        flash("File not found.", "error")
        return redirect(url_for("index"))

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        output_path = STORAGE_DIR / f"{file_id}_restored.tmp"
        with output_path.open("wb") as output:
            for block_name in manifest["block_files"]:
                # Only accept expected block filenames to avoid path traversal.
                if Path(block_name).name != block_name:
                    raise ValueError("Invalid block filename")
                encrypted = (BLOCKS_DIR / block_name).read_bytes()
                output.write(cipher.decrypt(encrypted))

        response = send_file(
            output_path,
            as_attachment=True,
            download_name=manifest["filename"],
        )
        response.call_on_close(lambda: output_path.unlink(missing_ok=True))
        return response
    except (OSError, ValueError, InvalidToken, KeyError, json.JSONDecodeError):
        flash("Could not restore the file. The encryption key or a stored block may be missing or damaged.", "error")
        return redirect(url_for("index"))


@app.errorhandler(413)
def too_large(_error):
    flash("File is too large. The maximum upload size is 50 MB.", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
