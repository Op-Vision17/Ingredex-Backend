from crewai import Task

from app.ai.prompts import (
    build_analyze_task_prompt,
    build_format_task_prompt,
    build_health_context_prompt,
)


def get_tasks(
    analyzer: object,
    formatter: object,
    product_name: str,
    ingredients_str: str,
    web_context: str = "",
    sources: list[dict] | None = None,
    health_profile: dict | None = None,
) -> tuple[Task, Task]:
    health_context = build_health_context_prompt(health_profile)
    analyze_prompt = build_analyze_task_prompt(
        product_name=product_name,
        ingredients_str=ingredients_str,
        health_context=health_context,
        web_context=web_context,
    )
    format_prompt = build_format_task_prompt(sources=sources)

    analyze_task = Task(
        description=analyze_prompt,
        expected_output="Detailed ingredient analysis with risks and benefits",
        agent=analyzer,
    )

    format_task = Task(
        description=format_prompt,
        expected_output="Raw JSON string only",
        agent=formatter,
        context=[analyze_task],
    )

    return analyze_task, format_task

