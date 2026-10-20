"""Verify self-improvement periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_self_improvement_verification() -> list:
    results = []

    # 1. knowledge-consolidation-weekly -> knowledge_consolidation()
    from backend.services.tasks.task_executor import knowledge_consolidation
    results.append(run_task("knowledge-consolidation-weekly", knowledge_consolidation))

    # 2. performance-optimization-weekly -> performance_optimization()
    from backend.services.tasks.task_executor import performance_optimization
    results.append(run_task("performance-optimization-weekly", performance_optimization))

    # 3. generate-auto-tools-weekly -> generate_auto_tools()
    from backend.services.tasks.task_executor import generate_auto_tools
    results.append(run_task("generate-auto-tools-weekly", generate_auto_tools))

    # 4. decay-learnings -> decay_learnings()
    from backend.services.tasks.task_executor import decay_learnings
    results.append(run_task("decay-learnings", decay_learnings))

    # 5. update-citation-boosts -> update_citation_boosts()
    from backend.services.tasks.task_executor import update_citation_boosts
    results.append(run_task("update-citation-boosts", update_citation_boosts))

    # 6. cleanup-citation-edges-weekly -> cleanup_citation_edges()
    from backend.services.tasks.task_executor import cleanup_citation_edges
    results.append(run_task("cleanup-citation-edges-weekly", cleanup_citation_edges))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_self_improvement_verification()