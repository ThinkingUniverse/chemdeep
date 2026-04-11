from .._common.interface import SkillInterface
from core.mcp_client import MCPClient
import os


MCP_COMMAND = os.environ.get("CHEMDEEP_MCP_COMMAND", "python")
MCP_ARGS = os.environ.get("CHEMDEEP_MCP_ARGS", "mcp_server/server.py").split()
MCP_ENV = os.environ.copy()
MCP_CWD = os.environ.get("CHEMDEEP_MCP_CWD", None)


class DeepResearchSkill(SkillInterface):
    def __init__(self):
        super().__init__(name="deep-research")
        self.client = MCPClient(MCP_COMMAND, MCP_ARGS, env=MCP_ENV, cwd=MCP_CWD)

    def _run(self, query, language, field, mode, **kwargs):
        if kwargs.get("prepare_live_browser_session"):
            self.client.call_tool(
                "prepare_live_browser_session",
                {
                    "purpose": kwargs.get(
                        "browser_purpose", "deep research full-text acquisition"
                    ),
                    "launch_if_needed": kwargs.get("launch_if_needed", True),
                    "article_url": kwargs.get("article_url", ""),
                    "doi": kwargs.get("doi", ""),
                    "title": kwargs.get("title", ""),
                },
            )

        result = self.client.call_tool(
            "run_deep_research",
            {
                "goal": query,
                "max_iterations": kwargs.get("max_iterations", 3),
                **(
                    {"min_year": kwargs.get("min_year")}
                    if kwargs.get("min_year") is not None
                    else {}
                ),
                "min_score": kwargs.get("min_score", 5),
                **(
                    {"previous_context": kwargs.get("previous_context")}
                    if kwargs.get("previous_context")
                    else {}
                ),
                "fetch_full_text": kwargs.get("fetch_full_text", False),
            },
            timeout=kwargs.get("timeout", 1800),
        )

        return {
            "skill": self.name,
            "query": query,
            "language": language,
            "field": field,
            "mode": mode,
            "result": result,
        }
