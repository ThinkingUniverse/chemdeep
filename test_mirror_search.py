"""
测试镜像检索功能
测试 MirrorManager 和 LanfanshuSearcher 的镜像优先策略
"""

import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.mirror_manager import (
    MirrorManager,
    get_env_direct_mirrors,
    get_env_nav_sources,
)
from core.scholar_search import LanfanshuSearcher

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_mirror_manager():
    """测试镜像管理器"""
    logger.info("=" * 60)
    logger.info("测试 MirrorManager")
    logger.info("=" * 60)

    # 测试 1: 检查环境变量
    logger.info("\n1. 检查环境变量 CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS")
    env_nav_sources = get_env_nav_sources()
    if env_nav_sources:
        logger.info(f"✅ 导航地址已设置，包含 {len(env_nav_sources)} 个来源:")
        for i, url in enumerate(env_nav_sources, 1):
            logger.info(f"   {i}. {url}")
    else:
        logger.info("ℹ️  导航地址未设置，将使用默认导航来源")

    logger.info("\n2. 检查环境变量 CHEMDEEP_LANFANSHU_MIRROR_URLS")
    env_direct_mirrors = get_env_direct_mirrors()
    if env_direct_mirrors:
        logger.info(f"✅ 直连镜像已设置，包含 {len(env_direct_mirrors)} 个地址:")
        for i, url in enumerate(env_direct_mirrors, 1):
            logger.info(f"   {i}. {url}")
    else:
        logger.info("ℹ️  直连镜像未设置，将仅使用默认镜像与导航解析结果")

    # 测试 3: 初始化镜像管理器
    logger.info("\n3. 初始化镜像管理器")
    mirror_manager = MirrorManager()
    all_mirrors = mirror_manager.get_all_mirrors()
    logger.info(f"✅ 镜像管理器初始化成功，共 {len(all_mirrors)} 个镜像")

    # 测试 4: 获取最佳镜像
    logger.info("\n4. 获取最佳镜像")
    best_mirror = mirror_manager.get_best_mirror()
    if best_mirror:
        logger.info(f"✅ 最佳镜像: {best_mirror.name} ({best_mirror.url})")
    else:
        logger.warning("⚠️  没有可用的镜像")

    # 测试 5: 获取所有可用镜像
    logger.info("\n5. 获取所有可用镜像")
    working_mirrors = mirror_manager.get_working_mirrors()
    logger.info(f"✅ 可用镜像数量: {len(working_mirrors)}")
    for i, mirror in enumerate(working_mirrors, 1):
        logger.info(f"   {i}. {mirror.name} ({mirror.url})")

    # 测试 6: 健康检查（可选，可能需要较长时间）
    logger.info("\n6. 执行健康检查（这可能需要一些时间）...")
    try:
        health_results = mirror_manager.check_all_mirrors()
        logger.info(f"✅ 健康检查完成，共检查 {len(health_results)} 个镜像")

        # 打印健康检查结果
        for result in health_results:
            status = "✅ OK" if result.is_healthy else "❌ FAIL"
            logger.info(
                f"   {status} {result.mirror.name}: "
                f"{result.response_time:.2f}s, "
                f"{'有结果' if result.has_results else '无结果'}"
            )
            if result.error:
                logger.info(f"      错误: {result.error}")
    except Exception as e:
        logger.error(f"❌ 健康检查失败: {e}")

    # 测试 7: 获取状态摘要
    logger.info("\n7. 获取状态摘要")
    summary = mirror_manager.get_status_summary()
    logger.info(f"\n{summary}")

    return mirror_manager


def test_lanfanshu_searcher():
    """测试 LanfanshuSearcher 的镜像优先策略"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 LanfanshuSearcher 镜像优先策略")
    logger.info("=" * 60)

    # 测试查询
    test_query = "machine learning"
    max_results = 5

    logger.info(f"\n1. 测试查询: '{test_query}'")
    logger.info(f"   最大结果数: {max_results}")

    # 初始化搜索器
    logger.info("\n2. 初始化 LanfanshuSearcher")
    try:
        searcher = LanfanshuSearcher()
        logger.info("✅ LanfanshuSearcher 初始化成功")
    except Exception as e:
        logger.error(f"❌ LanfanshuSearcher 初始化失败: {e}")
        return

    # 执行搜索
    logger.info(f"\n3. 执行搜索（将自动尝试镜像优先策略）...")
    logger.info("   注意：这可能需要一些时间，因为需要启动浏览器")

    try:
        result = searcher.search(test_query, max_results=max_results, headless=True)

        logger.info("\n4. 搜索结果:")
        logger.info(f"   成功: {result['success']}")
        logger.info(f"   找到论文数: {result['count']}")

        if result["success"] and result["papers"]:
            logger.info(f"\n   前 {min(3, len(result['papers']))} 篇论文:")
            for i, paper in enumerate(result["papers"][:3], 1):
                logger.info(f"   {i}. {paper.get('title', 'N/A')}")
                logger.info(f"      作者: {paper.get('authors', 'N/A')}")
                logger.info(f"      年份: {paper.get('year', 'N/A')}")
                logger.info(f"      URL: {paper.get('url', 'N/A')}")
        elif result.get("error"):
            logger.warning(f"   错误: {result['error']}")

    except Exception as e:
        logger.error(f"❌ 搜索失败: {e}")
        import traceback

        traceback.print_exc()


def main():
    """主函数"""
    logger.info("开始测试镜像检索功能\n")

    # 测试镜像管理器
    mirror_manager = test_mirror_manager()

    # 测试 LanfanshuSearcher
    test_lanfanshu_searcher()

    logger.info("\n" + "=" * 60)
    logger.info("测试完成")
    logger.info("=" * 60)

    # 提供使用说明
    logger.info("\n使用说明:")
    logger.info(
        "1. 要使用自定义导航页，设置环境变量 CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS"
    )
    logger.info("   例如（Windows PowerShell）:")
    logger.info(
        "   $env:CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS='https://ac.scmor.com/;https://your-nav.example.com/'"
    )
    logger.info("")
    logger.info("   例如（Linux/Mac）:")
    logger.info(
        "   export CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS='https://ac.scmor.com/;https://your-nav.example.com/'"
    )
    logger.info("")
    logger.info("2. 可选地补充直连镜像地址 CHEMDEEP_LANFANSHU_MIRROR_URLS:")
    logger.info(
        "   CHEMDEEP_LANFANSHU_MIRROR_URLS=https://scholar.lanfanshu.cn,https://sc.panda985.com"
    )
    logger.info("")
    logger.info("3. 或者在 .env 文件中添加:")
    logger.info("   CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS=https://ac.scmor.com/")
    logger.info("")
    logger.info("4. 系统会自动:")
    logger.info("   - 优先从导航页集合中提取镜像")
    logger.info("   - 合并直连镜像补充列表")
    logger.info("   - 测试镜像可用性")
    logger.info("   - 自动回退到下一个镜像")
    logger.info("   - 最终回退到原始的 xueshu.lanfanshu.cn")


if __name__ == "__main__":
    main()
