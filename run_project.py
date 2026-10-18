"""
Unified Project Runner for Veraxi YMMP.
Clean CLI wrapper delegating to veraxi_ymmp.pipeline.ProjectPipeline.
"""

import argparse
import sys
from veraxi_ymmp.pipeline import ProjectPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Veraxi YMMP Project Runner")
    parser.add_argument("project", type=str, help="Path to project directory")
    parser.add_argument("--no-premiere", action="store_true", help="Skip Premiere XML export")
    parser.add_argument("--no-ymmp", action="store_true", help="Skip YMM4 export")
    parser.add_argument("--no-qa", action="store_true", help="Skip MoviePy QA render")
    parser.add_argument("--qa-duration", type=float, default=30.0, help="Duration for QA render in seconds")
    parser.add_argument("--no-thumbnail", action="store_true", help="Skip YouTube thumbnail generation")

    args = parser.parse_args()
    pipeline = ProjectPipeline()
    result = pipeline.run(
        project_path=args.project,
        do_premiere=not args.no_premiere,
        do_ymmp=not args.no_ymmp,
        do_qa=not args.no_qa,
        qa_duration=args.qa_duration,
        do_thumbnail=not args.no_thumbnail,
    )
    if not result.success:
        for err in result.errors:
            print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
