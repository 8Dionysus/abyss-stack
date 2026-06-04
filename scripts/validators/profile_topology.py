from __future__ import annotations

from pathlib import Path
import re


PROFILE_DIR = Path("compose") / "profiles"
PRESET_DIR = Path("compose") / "presets"
MODULE_DIR = Path("compose") / "modules"
EXPECTED_PROFILES = {
    "substrate.txt": ["10-storage.yml"],
    "workflows.txt": ["10-storage.yml", "20-orchestration.yml"],
    "local-worker.txt": ["32-llamacpp-inference.yml", "41-agent-api.yml"],
    "intel-worker.txt": [
        "32-llamacpp-inference.yml",
        "31-intel-inference.yml",
        "41-agent-api.yml",
        "42-agent-api-intel.yml",
    ],
    "fallback-gateway.txt": ["30-local-inference.yml", "40-llm-gateway.yml"],
    "core.txt": ["10-storage.yml", "32-llamacpp-inference.yml"],
    "agentic.txt": [
        "10-storage.yml",
        "32-llamacpp-inference.yml",
        "41-agent-api.yml",
    ],
    "intel.txt": [
        "10-storage.yml",
        "32-llamacpp-inference.yml",
        "31-intel-inference.yml",
        "41-agent-api.yml",
        "42-agent-api-intel.yml",
    ],
}
EXPECTED_PRESETS = {
    "agent-federation.txt": ["substrate", "local-worker", "federation"],
    "agent-tools.txt": ["substrate", "local-worker", "tools"],
    "agent-observability.txt": ["substrate", "local-worker", "observability"],
    "agent-full.txt": ["substrate", "local-worker", "tools", "observability"],
    "intel-federation.txt": ["substrate", "intel-worker", "federation"],
    "intel-tools.txt": ["substrate", "intel-worker", "tools"],
    "intel-observability.txt": ["substrate", "intel-worker", "observability"],
    "intel-full.txt": ["substrate", "intel-worker", "tools", "observability"],
}
MODULE_REQUIREMENTS = {
    "20-orchestration.yml": {"10-storage.yml"},
    "40-llm-gateway.yml": {"30-local-inference.yml"},
    "41-agent-api.yml": {"32-llamacpp-inference.yml"},
    "42-agent-api-intel.yml": {"41-agent-api.yml", "31-intel-inference.yml"},
    "46-rag-api.yml": {
        "10-storage.yml",
        "31-intel-inference.yml",
        "41-agent-api.yml",
        "43-federation-router.yml",
        "45-rerank-api.yml",
    },
    "52-tos-graph.yml": {"10-storage.yml"},
}
PROFILE_README_REQUIRED_TEXT = (
    "`substrate`",
    "`workflows`",
    "`local-worker`",
    "`intel-worker`",
    "`fallback-gateway`",
    "`44-llamacpp-agent-sidecar.yml`",
)
N8N_EXTERNAL_RUNNER_SETTINGS = (
    "n8n-task-runners:",
    "N8N_RUNNERS_ENABLED",
    "N8N_RUNNERS_MODE: external",
    "N8N_RUNNERS_BROKER_LISTEN_ADDRESS: 0.0.0.0",
    "N8N_NATIVE_PYTHON_RUNNER",
    "N8N_RUNNERS_TASK_BROKER_URI: http://n8n:5679",
)
ACTIVE_ROUTE_PROFILE_DOCS = (
    Path("mechanics") / "config-projection" / "parts" / "rendering" / "docs" / "RENDER_TRUTH.md",
    Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "docs" / "DIAGNOSTIC_RUNTIME_PACKET.md",
    Path("mechanics") / "runtime-lifecycle" / "parts" / "start-stop" / "docs" / "LIVE_RUNTIME_CUTOVER_PACKET.md",
    Path("mechanics") / "federation-seams" / "parts" / "tos-graph" / "docs" / "TOS_GRAPH_CURATION.md",
    Path("mechanics") / "machine-fit" / "parts" / "fit-record" / "docs" / "PROFILE_MACHINE_FIT_PACKET.md",
)


def read_text(root: Path, relative_path: Path) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def load_names(path: Path) -> list[str]:
    names: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.append(line)
    return names


def validate_profiles(errors: list[str], *, root: Path) -> None:
    profile_dir = root / PROFILE_DIR
    module_dir = root / MODULE_DIR
    preset_dir = root / PRESET_DIR

    for profile_name, expected_modules in EXPECTED_PROFILES.items():
        profile_path = profile_dir / profile_name
        if not profile_path.exists():
            errors.append(f"missing required profile: {profile_path.relative_to(root)}")
            continue
        modules = load_names(profile_path)
        if modules != expected_modules:
            errors.append(
                f"profile {profile_name} must be {', '.join(expected_modules)}"
            )

    aoa_lib = read_text(root, Path("scripts") / "aoa-lib.sh")
    if 'AOA_STACK_DEFAULT_PROFILE="${AOA_STACK_DEFAULT_PROFILE:-substrate}"' not in aoa_lib:
        errors.append("scripts/aoa-lib.sh default profile must remain substrate")

    unit = read_text(root, Path("systemd") / "user" / "podman-compose-abyss.service")
    if "Environment=AOA_STACK_PROFILE=substrate" not in unit:
        errors.append("systemd/user/podman-compose-abyss.service must default to substrate")

    normal_profile_modules: dict[str, set[str]] = {}
    for profile in sorted(profile_dir.glob("*.txt")):
        modules = load_names(profile)
        if not modules:
            errors.append(f"profile has no modules: {profile.relative_to(root)}")
            continue
        normal_profile_modules[profile.name] = set(modules)

        seen = set(modules)
        for module_name in modules:
            module_path = module_dir / module_name
            if not module_path.exists():
                errors.append(
                    f"profile {profile.name} references missing module {module_name}"
                )

        for module_name, requirements in MODULE_REQUIREMENTS.items():
            if module_name not in seen:
                continue

            missing = sorted(
                requirement for requirement in requirements if requirement not in seen
            )
            if missing:
                errors.append(
                    f"profile {profile.name} includes {module_name} but is missing required modules: {', '.join(missing)}"
                )

    for profile_name, modules in normal_profile_modules.items():
        if "44-llamacpp-agent-sidecar.yml" in modules:
            errors.append(
                f"profile {profile_name} must not include 44-llamacpp-agent-sidecar.yml; route it through the inference-pilot sidecar"
            )

    modules_readme = read_text(root, MODULE_DIR / "README.md")
    profiles_readme = read_text(root, PROFILE_DIR / "README.md")
    for required_text in PROFILE_README_REQUIRED_TEXT:
        if required_text not in modules_readme:
            errors.append(f"compose/modules/README.md must mention {required_text}")
        if required_text not in profiles_readme:
            errors.append(f"compose/profiles/README.md must mention {required_text}")

    for preset_name, expected_profile_names in EXPECTED_PRESETS.items():
        preset_path = preset_dir / preset_name
        if not preset_path.exists():
            errors.append(f"missing required preset: {preset_path.relative_to(root)}")
            continue
        preset_profiles = load_names(preset_path)
        if preset_profiles != expected_profile_names:
            errors.append(
                f"preset {preset_name} must resolve to {', '.join(expected_profile_names)}"
            )

    github_workflow = read_text(root, Path(".github") / "workflows" / "validate-stack.yml")
    if "--profile intel-worker" not in github_workflow:
        errors.append(".github/workflows/validate-stack.yml must rehearse the intel-worker profile")
    if "--profile workflows" not in github_workflow:
        errors.append(".github/workflows/validate-stack.yml must rehearse the optional workflows profile")
    if (
        "--profile substrate --profile local-worker --profile tools --profile observability"
        not in github_workflow
    ):
        errors.append(
            ".github/workflows/validate-stack.yml must rehearse the composition-first agent-full profile set"
        )
    if "agentic,tools,observability" in github_workflow:
        errors.append(
            ".github/workflows/validate-stack.yml must not use agentic as the active combined route"
        )

    sidecar_module = read_text(root, MODULE_DIR / "44-llamacpp-agent-sidecar.yml")
    if 'AOA_FEDERATED_RUN_ENABLED: "true"' not in sidecar_module:
        errors.append(
            'compose/modules/44-llamacpp-agent-sidecar.yml must enable AOA_FEDERATED_RUN_ENABLED for governed advisory runs'
        )
    agent_api_module = read_text(root, MODULE_DIR / "41-agent-api.yml")
    if "AOA_FEDERATED_RUN_ENABLED:" in agent_api_module:
        errors.append(
            "compose/modules/41-agent-api.yml must not override AOA_FEDERATED_RUN_ENABLED so the runtime secret can control the gate"
        )

    orchestration_module = read_text(root, MODULE_DIR / "20-orchestration.yml")
    for snippet in N8N_EXTERNAL_RUNNER_SETTINGS:
        if snippet not in orchestration_module:
            errors.append(f"compose/modules/20-orchestration.yml must include n8n external runner setting: {snippet}")
    if not re.search(r"docker\.io/n8nio/runners:[^\s\"']+@sha256:[0-9a-f]{64}", orchestration_module):
        errors.append(
            "compose/modules/20-orchestration.yml must pin n8n-task-runners as docker.io/n8nio/runners:<version>@sha256:<digest>"
        )

    stack_env_example = read_text(root, Path("env") / "stack.env.example")
    if "N8N_RUNNERS_AUTH_TOKEN=CHANGE_ME_LONG_RANDOM_SHARED_SECRET" not in stack_env_example:
        errors.append("env/stack.env.example must include N8N_RUNNERS_AUTH_TOKEN placeholder for external n8n runners")

    service_catalog_doc = read_text(root, Path("docs") / "runtime" / "SERVICE_CATALOG.md")
    if "n8n-task-runners" not in service_catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention n8n-task-runners")

    warmup_script = read_text(
        root,
        Path("mechanics") / "runtime-lifecycle" / "parts" / "start-stop" / "aoa_warmup.sh",
    )
    deployment_doc = read_text(root, Path("docs") / "install" / "DEPLOYMENT.md")
    start_stop_readme = read_text(
        root,
        Path("mechanics") / "runtime-lifecycle" / "parts" / "start-stop" / "README.md",
    )
    if (
        "AOA_OLLAMA_WARMUP_ENABLED" not in warmup_script
        or "ollama warmup disabled" not in warmup_script
    ):
        errors.append(
            "aoa-warmup must keep Ollama fallback warmup behind AOA_OLLAMA_WARMUP_ENABLED"
        )
    if (
        "AOA_LLAMACPP_WARMUP_ENABLED" not in warmup_script
        or "llama.cpp warmup complete" not in warmup_script
    ):
        errors.append("aoa-warmup must keep llama.cpp local-worker warmup explicit")
    for required_text in (
        "AOA_OLLAMA_WARMUP_ENABLED=true",
        "`llama.cpp`",
        "Ollama",
    ):
        if required_text not in deployment_doc:
            errors.append(
                f"docs/install/DEPLOYMENT.md must mention {required_text} warmup posture"
            )
        if required_text not in start_stop_readme:
            errors.append(
                f"mechanics/runtime-lifecycle/parts/start-stop/README.md must mention {required_text} warmup posture"
            )

    for active_route_doc in ACTIVE_ROUTE_PROFILE_DOCS:
        active_route_text = read_text(root, active_route_doc)
        if "--profile core" in active_route_text:
            errors.append(
                f"{active_route_doc.as_posix()} must use substrate/local-worker/"
                "fallback-gateway or an explicit preset instead of --profile core"
            )

    secrets_doc = read_text(
        root,
        Path("mechanics")
        / "config-projection"
        / "parts"
        / "bootstrap"
        / "docs"
        / "SECRETS_BOOTSTRAP.md",
    )
    if "N8N_RUNNERS_AUTH_TOKEN" not in secrets_doc or "n8n-task-runners" not in secrets_doc:
        errors.append("mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md must describe the n8n runner shared token")


def validate_presets(errors: list[str], *, root: Path) -> None:
    profile_dir = root / PROFILE_DIR
    for preset in sorted((root / PRESET_DIR).glob("*.txt")):
        profiles = load_names(preset)
        if not profiles:
            errors.append(f"preset has no profiles: {preset.relative_to(root)}")
            continue

        for profile_name in profiles:
            profile_path = profile_dir / f"{profile_name}.txt"
            if not profile_path.exists():
                errors.append(
                    f"preset {preset.name} references missing profile {profile_name}"
                )
