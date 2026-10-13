
import os
import uuid
import hashlib
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, send_file
)
from cryptography.fernet import Fernet, InvalidToken
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from storage import make_storage

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BLOCK_SIZE = 1024 * 1024  # 1 MB
KEY_FILE = BASE_DIR / "secret.key"
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

if not KEY_FILE.exists():
    KEY_FILE.write_bytes(Fernet.generate_key())

cipher = Fernet(KEY_FILE.read_bytes())

app = Flask(__name__)
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY", "local-demo-only-change-before-deployment"
)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

storage = make_storage(BASE_DIR)


@app.get("/")
def index():
    items = []
    for manifest in storage.list_manifests():
        items.append({
            "id": manifest["id"],
            "filename": manifest["filename"],
            "blocks": manifest["blocks"],
            "size": manifest["size"],
        })
    return render_template("index.html", items=items)


@app.post("/upload")
def upload():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        flash("Please choose a file first.", "error")
        return redirect(url_for("index"))

    filename = secure_filename(uploaded.filename)
    if not filename:
        flash("Unsupported filename.", "error")
        return redirect(url_for("index"))

    file_id = uuid.uuid4().hex
    block_names = []
    total_size = 0

    try:
        block_count = 0
        while True:
            chunk = uploaded.stream.read(BLOCK_SIZE)
            if not chunk:
                break

            encrypted = cipher.encrypt(chunk)
            block_name = f"{file_id}_{block_count:05d}.bin"
            storage.put_block(block_name, encrypted)
            block_names.append(block_name)

            total_size += len(chunk)
            block_count += 1

        if block_count == 0:
            flash("The selected file is empty.", "error")
            return redirect(url_for("index"))

        manifest = {
            "id": file_id,
            "filename": filename,
            "size": total_size,
            "blocks": block_count,
            "block_files": block_names,
        }
        storage.put_manifest(file_id, manifest)
        flash(
            f"Upload successful! File encrypted and stored in "
            f"{block_count} block(s) ({storage.name} storage).",
            "success",
        )

    except Exception as error:
        app.logger.exception("Upload failed")
        for name in block_names:
            try:
                storage.delete_block(name)
            except Exception:
                app.logger.exception("Could not remove partial block")
        try:
            storage.delete_manifest(file_id)
        except Exception:
            pass
        flash(f"Upload failed: {type(error).__name__}. Check the terminal.", "error")

    return redirect(url_for("index"))


@app.get("/download/<file_id>")
def download(file_id):
    if not file_id.isalnum():
        flash("Invalid file ID.", "error")
        return redirect(url_for("index"))

    output_path = None
    try:
        manifest = storage.get_manifest(file_id)
        if not manifest:
            flash("File not found.", "error")
            return redirect(url_for("index"))

        output_path = STORAGE_DIR / f"{file_id}_restored.tmp"
        digest = hashlib.sha256()

        with output_path.open("wb") as output:
            for block_name in manifest["block_files"]:
                if Path(block_name).name != block_name:
                    raise ValueError("Invalid block filename")

                encrypted = storage.get_block(block_name)
                plaintext = cipher.decrypt(encrypted)
                output.write(plaintext)
                digest.update(plaintext)

        if output_path.stat().st_size != manifest["size"]:
            raise ValueError("Restored file size does not match")

        response = send_file(
            output_path,
            as_attachment=True,
            download_name=manifest["filename"],
        )
        response.call_on_close(lambda: output_path.unlink(missing_ok=True))
        return response

    except (OSError, ValueError, InvalidToken, KeyError) as error:
        app.logger.exception("Download failed")
        if output_path:
            output_path.unlink(missing_ok=True)
        flash(
            "Could not restore the file. The encryption key or a stored block "
            "may be missing or damaged.",
            "error",
        )
        return redirect(url_for("index"))
    except Exception:
        app.logger.exception("Storage download failed")
        if output_path:
            output_path.unlink(missing_ok=True)
        flash("Download failed. Check the terminal for details.", "error")
        return redirect(url_for("index"))


@app.errorhandler(413)
def too_large(_error):
    flash("File is too large. Maximum size is 50 MB.", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=False)
