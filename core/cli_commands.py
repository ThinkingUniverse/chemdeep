"""
CLI 命令模块

包含所有命令行接口命令
"""

import typer
from pathlib import Path

from core.services.research.types import ResearchPlan


def register_cli_commands(app: typer.Typer):
    """注册所有 CLI 命令到 Typer 应用"""

    def resolve_query(query: str | None, prompt_text: str) -> str:
        value = (query or "").strip()
        while not value:
            value = typer.prompt(prompt_text).strip()
        return value

    @app.command("search")
    def cli_search(
        query: str | None = typer.Argument(None, help="搜索关键词"),
        sources: str = typer.Option("openalex,crossref", help="数据源，逗号分隔"),
        max_results: int = typer.Option(50, help="最大结果数"),
    ):
        """命令行搜索"""
        from core.scholar_search import UnifiedSearcher

        query = resolve_query(query, "请输入搜索关键词")

        typer.echo(f"搜索: {query}")
        typer.echo(f"数据源: {sources}")

        searcher = UnifiedSearcher(notify_callback=lambda x: typer.echo(x))
        result = searcher.search(
            query, sources=sources.split(","), max_results=max_results
        )

        if result["success"]:
            typer.echo(f"\n找到 {result['count']} 篇论文")
            for i, p in enumerate(result["papers"][:10], 1):
                typer.echo(f"{i}. {p.get('title', '无标题')[:60]}")
                typer.echo(f"   DOI: {p.get('doi', '无')}")
        else:
            typer.echo(f"搜索失败: {result.get('errors')}")

    @app.command("models")
    def list_models(show_all: bool = typer.Option(False, "--all", help="显示全部模型")):
        """列出可用的 AI 模型"""
        from core.ai import AIClient

        typer.echo("正在获取模型列表...")
        ai = AIClient(notify_callback=lambda x: typer.echo(x))
        result = ai.list_models(show_all=show_all)
        typer.echo(result)

    @app.command("test-ai")
    def test_ai(
        prompt: str = typer.Option("你好，请用一句话介绍自己", help="测试 prompt"),
        model: str = typer.Option(None, help="指定模型"),
    ):
        """测试 AI 连接"""
        from core.ai import AIClient, MODEL_STATE

        ai = AIClient(notify_callback=lambda x: typer.echo(x))

        if model:
            MODEL_STATE.set_openai_model(model)
            typer.echo(f"使用模型: {model}")
        else:
            typer.echo(f"使用模型: {MODEL_STATE.openai_model}")

        typer.echo(f"Prompt: {prompt}")
        typer.echo("正在调用 AI...")

        result = ai.call(prompt, json_mode=False)

        if result.success:
            response_data = result.data if isinstance(result.data, dict) else {}
            response_text = (
                response_data.get("text") or result.raw_response or result.data
            )
            typer.echo(f"\n✅ 调用成功!")
            typer.echo(f"Provider: {result.provider}")
            typer.echo(f"Model: {result.model}")
            typer.echo(f"Response:\n{response_text}")
        else:
            typer.echo(f"\n❌ 调用失败: {result.error}")

    @app.command("status")
    def show_status(limit: int = 5):
        """显示最近任务状态"""
        from utils.db import DB

        db = DB()
        rows = db.list_jobs(limit=limit)

        if not rows:
            typer.echo("暂无任务记录")
            return

        typer.echo("最近任务:")
        for r in rows:
            typer.echo(
                f"  {r['job_id']}  {r['status']:9s}  goal={r['goal']:<11s}  msg={r['message'] or ''}"
            )

    @app.command("init")
    def init_config():
        """初始化配置文件"""
        env_template = """# Telegram Bot 配置
CHEMDEEP_TELEGRAM_TOKEN=your_bot_token_here
CHEMDEEP_TELEGRAM_PROXY=socks5h://127.0.0.1:7890
CHEMDEEP_TELEGRAM_CHAT_ID=your_chat_id
CHEMDEEP_TELEGRAM_ALLOWED_CHAT_IDS=your_chat_id

# AI Provider 配置 (openai | gemini | auto)
CHEMDEEP_AI_PROVIDER=openai

# OpenAI 兼容 API
CHEMDEEP_OPENAI_API_KEY=sk-xxx
CHEMDEEP_OPENAI_API_BASE=https://api.openai.com/v1
CHEMDEEP_OPENAI_MODEL=gpt-4-turbo-preview

# Google Gemini
CHEMDEEP_GEMINI_API_KEY=
CHEMDEEP_GEMINI_MODEL=gemini-1.5-pro

# AI 请求行为
CHEMDEEP_AI_TIMEOUT=60
CHEMDEEP_AI_MAX_RETRIES=3

# 路径配置
CHEMDEEP_PROFILE_DIR=profiles/msedge
CHEMDEEP_LIBRARY_DIR=data/library
CHEMDEEP_REPORTS_DIR=data/reports

# 全文抓取默认开关（0=默认关闭，1=默认开启；命令行参数可覆盖）
CHEMDEEP_DEFAULT_FETCH_FULL_TEXT=0

# 浏览器行为配置
CHEMDEEP_RATE_SECONDS=75
CHEMDEEP_HEADLESS=0
CHEMDEEP_BROWSER_CHANNEL=msedge

# Google Scholar
CHEMDEEP_ENABLE_GOOGLE_SCHOLAR=1
CHEMDEEP_GOOGLE_SCHOLAR_DELAY=5
"""
        env_path = Path("config/.env")
        if env_path.exists():
            typer.echo(f"配置文件已存在: {env_path}")
            overwrite = typer.confirm("是否覆盖?")
            if not overwrite:
                return
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(env_template, encoding="utf-8")
        typer.echo(f"✅ 已创建配置文件: {env_path}")
        typer.echo("请编辑配置文件填入你的 API 密钥和 Telegram 信息")

    @app.command("config")
    def show_config():
        """显示当前配置"""
        from config.settings import settings

        typer.echo(settings.summary())

    @app.command("login")
    def login_browser(
        url: str = typer.Option("https://www.webofscience.com", help="登录网址"),
    ):
        """打开浏览器登录 WoS/Scholar"""
        from core.wos_search import WoSSearcher

        typer.echo(f"正在打开浏览器: {url}")
        typer.echo("请在浏览器中完成登录，完成后关闭窗口")
        searcher = WoSSearcher(notify_callback=lambda x: typer.echo(x))
        searcher.login_interactive()

    @app.command("setmodel")
    def cli_setmodel(model: str):
        """设置 AI 模型"""
        from core.ai import MODEL_STATE

        old = MODEL_STATE.openai_model
        MODEL_STATE.set_openai_model(model)
        typer.echo(f"模型已切换: {old} -> {model}")

    @app.command("currentmodel")
    def cli_currentmodel():
        """显示当前模型"""
        from core.ai import MODEL_STATE
        from config.settings import settings

        typer.echo(f"OpenAI 模型: {MODEL_STATE.openai_model}")
        typer.echo(f"Gemini 模型: {MODEL_STATE.gemini_model}")
        typer.echo(f"API Base: {settings.OPENAI_API_BASE}")
        typer.echo(f"Provider: {settings.AI_PROVIDER}")

    @app.command("research")
    def cli_research(
        query: str | None = typer.Argument(None, help="研究主题或问题"),
        max_results: int = typer.Option(20, help="最大文献数量"),
        quick: bool = typer.Option(False, help="快速模式，跳过计划确认"),
        year5: bool = typer.Option(False, help="仅近5年文献"),
        year10: bool = typer.Option(False, help="仅近10年文献"),
        year: int = typer.Option(None, help="指定最早年份，含"),
        min_score: float = typer.Option(0.0, help="论文最小评分 (0-10)"),
        fetch_full_text: bool | None = typer.Option(
            None,
            "--fetch-full-text/--no-fetch-full-text",
            help="尝试获取论文全文；未指定时跟随环境变量 CHEMDEEP_DEFAULT_FETCH_FULL_TEXT",
        ),
        generate_report: bool = typer.Option(
            False, "--generate-report", help="运行完整迭代流程并生成详细报告"
        ),
    ):
        """执行深度研究"""
        from core.services.research.main import DeepResearcher

        query = resolve_query(query, "请输入研究主题或问题")

        typer.echo(f"🔬 开始深度研究: {query}")
        typer.echo(f"📊 最大文献数: {max_results}")
        typer.echo(f"⚡ 快速模式: {quick}")
        typer.echo(
            f"📄 全文抓取: {'环境默认' if fetch_full_text is None else fetch_full_text}"
        )
        typer.echo("-" * 50)

        researcher = DeepResearcher(notify_callback=lambda x: typer.echo(x))

        try:
            # 1. 生成研究计划
            typer.echo("📋 正在生成研究计划...")
            plan = researcher.generate_plan(query)
            clarification_text = ""

            # 先生成澄清问题（和Bot一致）
            clarifications = researcher.planner.generate_clarifying_questions(query)
            if clarifications:
                typer.echo("\n✍️  为了更好地定位研究需求，建议回答以下澄清问题：")
                for idx, c in enumerate(clarifications, 1):
                    typer.echo(f"  {idx}. {c}")

                # only ask interactive answers when not quick
                if not quick:
                    answers = []
                    for c in clarifications:
                        ans = typer.prompt(f"请回答: {c} (可直接回车跳过)", default="")
                        if ans:
                            answers.append(ans)
                    clarification_text = "\n".join(
                        [f"{i + 1}. {a}" for i, a in enumerate(answers)]
                    )
                    if clarification_text:
                        typer.echo("\n✅ 已记录澄清问题回答（用于内部分析）：")
                        typer.echo(clarification_text)

            compatible_plan = ResearchPlan(
                question=query,
                objectives=list(plan.objectives),
                search_queries=list(plan.search_queries),
                analysis_focus=plan.analysis_focus,
                key_aspects=list(plan.key_aspects),
                criteria=dict(plan.criteria),
            )

            # 显示研究计划文本
            if not quick:
                plan_text = researcher.format_plan(compatible_plan)
                typer.echo("\n" + "=" * 50)
                typer.echo("📋 研究计划:")
                typer.echo("=" * 50)
                typer.echo(plan_text)
                typer.echo("=" * 50)

                if not typer.confirm("是否按此计划执行研究?"):
                    typer.echo("❌ 已取消")
                    return

            # 2. 年限参数
            min_year = None
            if year5:
                from datetime import datetime

                min_year = datetime.now().year - 5
            elif year10:
                from datetime import datetime

                min_year = datetime.now().year - 10
            elif year:
                min_year = year

            if min_year:
                typer.echo(f"📅 年份筛选: >= {min_year}")
            if min_score and min_score > 0:
                typer.echo(f"🏷️ 最低得分筛选: >= {min_score}")

            # 3. 执行搜索
            typer.echo("\n🔍 正在执行文献搜索...")
            search_result = researcher.execute_search(
                compatible_plan,
                max_per_source=50,
                top_n=max_results,
                min_year=min_year,
                min_score=min_score,
                fetch_full_text=fetch_full_text,
            )

            papers = search_result.get("papers", [])
            typer.echo(f"\n✅ 搜索完成!")
            typer.echo(f"📚 找到文献: {len(papers)} 篇")
            typer.echo(f"🔗 数据源: {', '.join(search_result.get('sources_used', []))}")

            if papers:
                typer.echo("\n📖 文献列表:")
                for i, paper in enumerate(papers[:10], 1):  # 只显示前10篇
                    title = paper.get("title", "无标题")[:60]
                    authors = (
                        paper.get("authors", ["未知"])[0]
                        if paper.get("authors")
                        else "未知"
                    )
                    year = paper.get("year", "未知")
                    score = paper.get("screening", {}).get("total_score", "N/A")
                    typer.echo(f"  {i}. [{score}] {title}...")
                    typer.echo(f"     作者: {authors} | 年份: {year}")

                if len(papers) > 10:
                    typer.echo(f"  ... 还有 {len(papers) - 10} 篇文献")

            # 3. 生成报告 (如果有足够的文献)
            if len(papers) >= 3:
                if generate_report:
                    typer.echo(
                        "\n📝 正在运行迭代式研究并生成详细报告（与 Bot 等效）..."
                    )
                    iter_result = researcher.run_iterative_research(
                        query, max_iterations=1, fetch_full_text=fetch_full_text
                    )
                    report_path = iter_result.get("report_path")
                    synthesis_text = iter_result.get("result", {}).get(
                        "synthesis_text", ""
                    )
                    if report_path:
                        typer.echo(f"📄 报告已生成: {report_path}")
                    if synthesis_text:
                        preview = synthesis_text[:4000]
                        typer.echo("\n📌 报告摘要 (前 4000 字):\n")
                        typer.echo(preview)
                else:
                    typer.echo("\n📝 本次仅执行文献搜索与筛选，未生成详细研究报告文件")
                    typer.echo("ℹ️ 如需生成 report.md，请添加参数 --generate-report")
                    typer.echo(
                        "ℹ️ 报告默认保存到 data/library/deep_research/dr_iter_<timestamp>/report.md"
                    )
            else:
                typer.echo("\n⚠️ 文献数量不足，无法生成完整报告")

            typer.echo("\n🎉 深度研究完成!")

        except Exception as e:
            typer.echo(f"❌ 研究失败: {e}")
            import traceback

            typer.echo(traceback.format_exc())
