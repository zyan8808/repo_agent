from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from repo_agent.contracts import AgentRequest, AgentResult, InferenceRequest, InferenceResult


@workflow.defn
class AgentWorkflow:
    @workflow.run
    async def run(self, request: AgentRequest) -> AgentResult:
        inference_request = InferenceRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a repository agent. Be precise and return actionable results."
                    ),
                },
                {"role": "user", "content": request.prompt},
            ],
            model="agent-default",
        )
        result = await workflow.execute_activity(
            "run_inference",
            inference_request,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                maximum_interval=timedelta(minutes=1),
                maximum_attempts=4,
            ),
            result_type=InferenceResult,
        )
        return AgentResult(output=result.content, model=result.model)