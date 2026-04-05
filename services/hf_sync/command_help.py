"""Help text for hf_sync command interface."""


def _help_text() -> str:
    return (
        "hf_sync S3 actions:\n"
        '- upload: {"action":"upload","path":"/abs/file.png","key":"assets/cover.png","encrypt":false}\n'
        '- upload_text: {"action":"upload_text","key":"notes/today.txt","text":"hello","encrypt":true}\n'
        '- upload_b64: {"action":"upload_b64","key":"blobs/blob.dat","content_b64":"...","content_type":"image/png","encrypt":false}\n'
        '- list: {"action":"list"}\n'
        '- url: {"action":"url","key":"assets/cover.png"}\n'
        '- delete: {"action":"delete","key":"assets/cover.png"}'
    )
