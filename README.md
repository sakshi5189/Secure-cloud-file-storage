# Secure Cloud File Storage System

A beginner-friendly Cloud Computing mini-project demonstrating file chunking, encryption, local storage, and restoration.

## Features
- Browser-based file upload
- Splits files into 1 MB blocks
- Encrypts each block with Fernet (authenticated symmetric encryption)
- Stores encrypted blocks and a JSON manifest
- Decrypts and reconstructs the original file for download
- Simple responsive HTML/CSS interface

## Requirements
- Python 3.10 or newer
- Internet only for the first-time package installation

## Run on Windows
1. Extract the ZIP folder.
2. Open Command Prompt in the extracted folder.
3. Create and activate a virtual environment (recommended):
   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   ```
4. Install packages:
   ```bat
   py -m pip install -r requirements.txt
   ```
5. Start the app:
   ```bat
   py app.py
   ```
6. Open `http://127.0.0.1:5000` in your browser.

## Run on macOS/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```
Then open `http://127.0.0.1:5000`.

## How to demonstrate
1. Upload a text file or image.
2. Show the generated encrypted `.bin` blocks in `storage/blocks/`.
3. Open the corresponding JSON file in `storage/manifests/` to show the number of blocks.
4. Download the file and compare it with the original.
5. Explain that encrypted blocks are decrypted and joined in the original order.

## Important limitations
This is a local educational prototype, not a production cloud service. It does not yet use AWS S3, Azure Blob Storage, Google Cloud Storage, or CloudFront. For real deployment, use cloud object storage, HTTPS, authentication, access controls, and a managed key service. Keep `secret.key` safe: if it is lost, stored files cannot be decrypted. Do not expose the Flask development server to the public internet.
