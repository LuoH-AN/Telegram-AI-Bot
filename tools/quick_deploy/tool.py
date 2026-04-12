"""AI tool for quick static project deployment."""

from __future__ import annotations

from ..core.base import BaseTool
from services.deployments import delete_deployment, deploy_from_files, deploy_from_path, get_deployment, list_deployments


class QuickDeployTool(BaseTool):
    @property
    def name(self) -> str:
        return "quick_deploy"

    def definitions(self) -> list[dict]:
        return [{"type": "function", "function": {"name": self.name, "description": "Deploy static frontend projects such as HTML/CSS/JavaScript sites or build output folders, then return a public URL.", "parameters": self._parameters()}}]

    def _parameters(self) -> dict:
        return {"type": "object", "properties": {"action": {"type": "string", "enum": ["inspect", "deploy_path", "deploy_files", "delete", "url"]}, "source_path": {"type": "string", "description": "Repo-relative path to a static site folder or HTML file."}, "slug": {"type": "string", "description": "Public deployment slug."}, "entry_path": {"type": "string", "description": "Entry file for deploy_files, default index.html."}, "files": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Inline files map for deploy_files, e.g. {\"index.html\":\"...\",\"style.css\":\"...\"}"}}, "required": ["action"]}

    def get_instruction(self) -> str:
        return "\nQuick deploy tool usage:\n- Use quick_deploy to publish static frontend projects and return a URL.\n- Prefer deploy_files for small HTML/CSS/JS demos.\n- Prefer deploy_path for existing build output folders that already contain index.html.\n"

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        del user_id, tool_name
        action = str(arguments.get("action", "")).strip().lower()
        if action == "inspect":
            items = list_deployments()
            return "Deployments:\n" + ("\n".join(f"- {item['slug']}: {item.get('url','')}" for item in items) or "(none)")
        if action == "deploy_path":
            item = deploy_from_path(str(arguments.get("source_path", "")).strip(), slug=str(arguments.get("slug", "")).strip())
            return f"Deployed '{item['slug']}' at {item['url']}"
        if action == "deploy_files":
            item = deploy_from_files(dict(arguments.get("files") or {}), slug=str(arguments.get("slug", "")).strip(), entry_path=str(arguments.get("entry_path") or "index.html").strip() or "index.html")
            return f"Deployed '{item['slug']}' at {item['url']}"
        if action == "delete":
            slug = str(arguments.get("slug", "")).strip()
            return f"Deleted deployment '{slug}'." if delete_deployment(slug) else "Deployment not found."
        if action == "url":
            item = get_deployment(str(arguments.get("slug", "")).strip())
            return item.get("url", "") if item else "Deployment not found."
        return "Error: invalid action. Use inspect, deploy_path, deploy_files, delete, or url."
