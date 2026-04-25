"""Help text for the HF object command interface."""


def _help_text() -> str:
    return (
        "hf_sync S3 actions:\n"
        "default encrypt=false (plaintext object by key)\n"
        '- upload: {"action":"upload","path":"/abs/file.png","key":"assets/cover.png","encrypt":false}\n'
        '- upload_text: {"action":"upload_text","key":"notes/today.txt","text":"hello","encrypt":false}\n'
        '- upload_b64: {"action":"upload_b64","key":"blobs/blob.dat","content_b64":"...","content_type":"image/png","encrypt":false}\n'
        '- list: {"action":"list"} (legacy per-user index view)\n'
        '- ls: {"action":"ls","prefix":"assets/","recursive":true,"limit":200}\n'
        '- head: {"action":"head","key":"assets/cover.png"}\n'
        '- exists: {"action":"exists","key":"assets/cover.png"}\n'
        '- get_text: {"action":"get_text","key":"notes/today.txt","encoding":"utf-8"}\n'
        '- get_b64: {"action":"get_b64","key":"assets/cover.png"}\n'
        '- copy: {"action":"copy","src_key":"a.txt","dst_key":"backup/a.txt","overwrite":true}\n'
        '- move: {"action":"move","src_key":"a.txt","dst_key":"archive/a.txt","overwrite":true}\n'
        '- url: {"action":"url","key":"assets/cover.png"}\n'
        '- delete: {"action":"delete","key":"assets/cover.png"}\n'
        '- delete_prefix: {"action":"delete_prefix","prefix":"tmp/"}'
    )
