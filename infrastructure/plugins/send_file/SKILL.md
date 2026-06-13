---
name: send_file
version: 1.0.0
description: Send media (images, documents, voice, video) directly to the user in the active chat. Source can be a URL, a local file path, or an AI-generated image prompt.
entry_point: infrastructure.plugins.send_file.tool:SendFileTool
capabilities: [send_image, send_document, send_voice, send_video, generate_image]
platforms: [telegram]
---

# send_file

Sends a media message back into the current conversation.

**Use cases:**
- Share a picture you fetched from the web
- Deliver a document you wrote out to disk via the `terminal` tool
- Reply with a voice note or short video

**Important:** This tool only works inside an active user reply — it sends to the chat that triggered the current AI run. It cannot deliver to arbitrary users.

## Quick reference

| Goal | Arguments |
| ---- | --------- |
| Send an online image | `kind=image source=url url="https://..."` |
| Send a local file | `kind=document source=path path="/tmp/report.pdf" filename="report.pdf"` |
| Generate + send an image | `kind=image source=generate prompt="a red panda eating bamboo"` |
| Send a voice file | `kind=voice source=path path="/tmp/clip.mp3"` |
| Send a video file | `kind=video source=url url="https://..../clip.mp4"` |

`caption` is optional and best kept short. Filenames default sensibly per kind.
