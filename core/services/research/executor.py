"""
Research Search Executor
"""
import logging
from typing import Callable, Any
from core.mcp_search import MCPSearcher
from .types import ResearchPlan

logger = logging.getLogger('deep_research')

class SearchExecutor:
    def __init__(self, notify: Callable[[str], None]):
        self.notify = notify
        self.mcp = MCPSearcher()

    def execute(
        self,
        plan: ResearchPlan,
        max_per_source: int = 50,
        min_year: int | None = None,
        min_score: float | None = None,
    ) -> dict:
        """执行多源搜索"""
        self.notify("🔍 开始执行搜索 (MCP)...")

        all_papers = []
        seen_dois = set()
        sources_used = []
        errors = {}

        for query_config in plan.search_queries:
            self._execute_single_query(
                query_config,
                max_per_source,
                all_papers,
                seen_dois,
                sources_used,
                errors,
            )

        # 年限过滤（旧API路径）
        if min_year is not None:
            try:
                from .paper_scorer import paper_scorer

                initial_count = len(all_papers)
                all_papers = paper_scorer.filter_by_year(all_papers, min_year=min_year)
                self.notify(
                    f"📅 年份筛选 (≥{min_year}): {initial_count} -> {len(all_papers)} 篇"
                )
            except Exception as e:
                self.notify(f"⚠️ 年份筛选失败: {e}")

        if min_score is not None and min_score > 0:
            try:
                from .paper_scorer import paper_scorer

                initial_count = len(all_papers)
                # 先确保score存在
                for paper in all_papers:
                    if "score" not in paper:
                        score_result = paper_scorer.score_paper(paper)
                        paper["score"] = score_result["score"]
                all_papers = [p for p in all_papers if (p.get("score") or 0) >= min_score]
                self.notify(
                    f"🏷️ 分数筛选 (≥{min_score}): {initial_count} -> {len(all_papers)} 篇"
                )
            except Exception as e:
                self.notify(f"⚠️ 分数筛选失败: {e}")

        self.notify(f"📊 搜索完成: 共找到 {len(all_papers)} 篇论文")
        return {
            "papers": all_papers,
            "count": len(all_papers),
            "sources_used": list(set(sources_used)),
            "errors": errors,
        }

    def _execute_single_query(self, query: dict, max_res: int, 
                              all_papers: list, seen: set, sources: list, errors: dict):
        keywords = query.get("keywords", "")
        source = query.get("source", "crossref")
        
        if not keywords:
            return

        try:
            self.notify(f"📚 搜索 {source.upper()}: {keywords[:50]}...")
            
            result = self._dispatch_search(query, keywords, max_res)
            
            if result["success"]:
                sources.append(source)
                papers = result.get("papers", [])
                self.notify(f"  - 找到 {len(papers)} 篇论文")
                
                for p in papers:
                    self._process_paper(p, all_papers, seen)
            else:
                msg = result.get("error", "Unknown error")
                errors[source] = msg
                logger.error(f"搜索 {source} 失败: {msg}")
                
        except Exception as e:
            logger.error(f"搜索 {source} 异常: {e}")
            errors[source] = str(e)

    def _dispatch_search(self, query_config: dict, kw: str, max_res: int) -> dict:
        source = str(query_config.get("source", "")).lower()
        year_low = query_config.get("yearLow") or query_config.get("year")
        year_high = query_config.get("yearHigh")

        # Source specific search calls
        if source == "wos":
            return self.mcp.search_wos(kw, max_results=max_res)
        elif source == "scholar":
            return self.mcp.search_google_scholar(
                kw,
                max_results=max_res,
                yearLow=year_low,
                yearHigh=year_high,
            )
        elif source == "openalex":
            return self.mcp.search_openalex(
                kw,
                max_results=max_res,
                year=year_low,
            )
        elif source == "lanfanshu":
            return self.mcp.search_lanfanshu(
                kw,
                max_results=max_res,
                yearLow=year_low,
                yearHigh=year_high,
            )

        platform = "crossref" if source == "crossref" else source
        return self.mcp.search_papers(
            kw,
            platform=platform,
            max_results=max_res,
            year=year_low,
        )

    def _process_paper(self, p: dict, all_papers: list, seen: set):
        doi = p.get("doi", "")
        # Normalize authors
        authors = p.get("authors", [])
        if isinstance(authors, list):
            p["authors"] = ", ".join(authors)
            
        # Extract year
        if "year" not in p and "publishedDate" in p:
            try:
                p["year"] = int(p["publishedDate"][:4])
            except:
                pass
                
        if doi and doi.lower() not in seen:
            seen.add(doi.lower())
            all_papers.append(p)

# --- Phase A-4: Executor "State-Only" Interface ---
from .types import ResearchState

def search(state: ResearchState) -> ResearchState:
    """
    [New] 纯状态驱动的搜索逻辑
    输入: state.plan (search_queries)
    输出: state.paper_pool (更新)
    """
    def temp_notify(msg):
        logger.info(msg)
        
    plan = state.plan
    if not plan or not plan.search_queries:
        logger.warning("No search plan or queries found.")
        return state
        
    executor = SearchExecutor(temp_notify)
    
    # We might want to pass existing papers to avoid duplicates if this runs iteratively?
    # For now, simplistic execution.
    
    # Needs ResearchPlan type for `execute` method signature if strictly typed
    # executor.execute expects ResearchPlan (V1)
    # We construct a V1 Plan or update executor.execute?
    # Let's mock a Plan object or duck type it since Python.
    # plan (ResearchPlanV2) has search_queries, which is list[dict].
    # execute iterates over plan.search_queries.
    
    result = executor.execute(plan, max_per_source=20)
    
    new_papers = result.get("papers", [])
    
    # Deduplicate against existing pool
    existing_dois = {p.get("doi", "").lower() for p in state.paper_pool if p.get("doi")}
    
    for p in new_papers:
        doi = (p.get("doi") or "").lower()
        if not doi or doi not in existing_dois:
            state.paper_pool.append(p)
            if doi: existing_dois.add(doi)
            
    # Update intermediate results?
    state.intermediate_results["search_count"] = len(state.paper_pool)
    
    return state
