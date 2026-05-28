import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from app.schema.chat import ChatRequest

# templates/ 디렉토리 기준으로 Jinja2 환경 설정
_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_system_prompt(request: ChatRequest, max_length: int) -> str:
    """
    ChatRequest를 받아 모드에 맞는 시스템 프롬프트를 조립한다.

    - problem_set 있음 → 문제풀이 모드 (system_problem.j2)
    - problem_set 없음 → 자유질문 모드 (system_free.j2)
    """
    if request.problem_set is not None:
        return _build_problem_prompt(request, max_length)
    return _build_free_prompt(max_length)


def _build_problem_prompt(request: ChatRequest, max_length: int) -> str:
    template = _env.get_template("system_problem.j2")

    current_problem_number = 1
    if request.session_progress:
        current_problem_number = request.session_progress.current_problem_number

    # dataset.meta_data JSON string → 리스트로 파싱
    dataset_columns: list[str] = []
    if request.dataset:
        try:
            dataset_columns = json.loads(request.dataset.meta_data)
        except (json.JSONDecodeError, TypeError):
            dataset_columns = []

    return template.render(
        problem_set=request.problem_set,
        problems=request.problems or [],
        current_problem_number=current_problem_number,
        dataset=request.dataset,
        dataset_columns=dataset_columns,
        max_length=max_length,
    )


def _build_free_prompt(max_length: int) -> str:
    template = _env.get_template("system_free.j2")
    return template.render(max_length=max_length)
