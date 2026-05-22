import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.orchestrator import HarnessOrchestrator
from core.config import ConfigLoader
from core.workspace import NovelWorkspace, init_workspace, list_novels

def main():
    parser = argparse.ArgumentParser(description="Harness 小说写作 Agent")
    parser.add_argument("--novel", type=str, default=None,
                        help="工作区名称（ novels/ 目录下的子目录名）")
    parser.add_argument("--action", choices=["gen-outlines", "gen-adaptive-outlines",
                        "write-chapters", "write-adaptive-chapters",
                        "write-pipeline",
                        "update-state", "update-adaptive-state", "all", "list"],
                        default="all", help="执行的动作（默认全部执行）")
    parser.add_argument("--start-chapter", type=int, default=1, help="起始章节号")
    parser.add_argument("--max-chapters", type=int, default=None, help="最大章节数")
    parser.add_argument("--max-batches", type=int, default=None, help="仿写模式：最多生成多少个10章批次")
    parser.add_argument("--chapter-num", type=int, default=None, help="指定更新状态的章节号")
    parser.add_argument("--outlines-dir", type=str, default=None, help="参考大纲目录（仿写模式用）")
    parser.add_argument("--inspiration-dir", type=str, default=None, help="灵感库目录（仿写模式用）")
    parser.add_argument("--self-check", action="store_true", help="生成正文后执行自检+修订，修订版保存为 _fix 文件")
    parser.add_argument("--parallel", action="store_true", help="并行模式：三个模型同时生成+融合")
    args = parser.parse_args()

    # --list 不需要工作区
    if args.action == "list":
        novels = list_novels()
        if novels:
            print("已有工作区：")
            for name in novels:
                print(f"  - {name}")
        else:
            print("暂无工作区。使用 --novel <名称> 指定工作区运行。")
        return

    # --novel 必填（除了 --list）
    if not args.novel:
        parser.error("请通过 --novel 指定工作区名称。使用 --action list 查看已有工作区。")

    print(f">>> Harness 小说写作 Agent 启动（工作区：{args.novel}）<<<")

    ws = init_workspace(args.novel)

    agent_configs = ConfigLoader.get_agent_configs()
    agent_configs["parallel_drafting"] = ConfigLoader.get_parallel_drafting_configs()
    agent_configs["fusion"] = ConfigLoader.get_fusion_config()
    agent_configs["state_update"] = ConfigLoader.get_state_update_config()
    orchestrator = HarnessOrchestrator(
        base_dir=ws.file_system,
        agent_configs=agent_configs,
    )

    if args.action in ("gen-outlines", "all"):
        orchestrator.generate_volume_outlines()

    if args.action == "gen-adaptive-outlines":
        orchestrator.generate_adaptive_outlines(
            outlines_dir=args.outlines_dir or ws.reference_outlines,
            inspiration_dir=args.inspiration_dir or ws.inspirations,
            max_batches=args.max_batches
        )

    if args.action in ("write-chapters", "all"):
        orchestrator.write_volume(start_chapter=args.start_chapter, max_chapters=args.max_chapters)

    if args.action == "write-adaptive-chapters":
        orchestrator.write_adaptive_chapters(
            start_chapter=args.start_chapter,
            max_chapters=args.max_chapters,
            self_check=args.self_check,
            parallel=args.parallel,
        )

    if args.action == "write-pipeline":
        orchestrator.write_pipeline(
            start_chapter=args.start_chapter,
            max_chapters=args.max_chapters or 10,
            self_check=args.self_check,
            parallel=args.parallel,
        )

    if args.action in ("update-state", "all"):
        if args.action == "all" and args.max_chapters is None:
            print("\n[提示] 正文已生成。确认内容无误后，请运行：python3 writing/main.py --action update-state")
        else:
            orchestrator.update_state(chapter_num=args.chapter_num)

    if args.action == "update-adaptive-state":
        orchestrator.update_adaptive_state(max_chapters=args.max_chapters)

    print(">>> 运行结束 <<<")

if __name__ == "__main__":
    main()
