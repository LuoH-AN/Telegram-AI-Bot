"""Static deployment helpers."""

from .deploy import deploy_from_files, deploy_from_path
from .manage import delete_deployment, get_deployment, list_deployments
from .meta import deployment_url, load_manifest, save_manifest
from .paths import DEPLOY_ROOT, deployment_dir, ensure_deploy_root, manifest_path, safe_child

__all__ = [
    "DEPLOY_ROOT",
    "delete_deployment",
    "deploy_from_files",
    "deploy_from_path",
    "deployment_dir",
    "deployment_url",
    "ensure_deploy_root",
    "get_deployment",
    "list_deployments",
    "load_manifest",
    "manifest_path",
    "safe_child",
    "save_manifest",
]
