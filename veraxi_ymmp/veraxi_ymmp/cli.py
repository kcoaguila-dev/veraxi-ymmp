import argparse
import json
from .compiler import YMMPCompiler

def main():
    parser = argparse.ArgumentParser(description="Generate YMM4 .ymmp timelines from a template and script.")
    parser.add_argument("template", help="Path to the template .ymmp file")
    parser.add_argument("script", help="Path to the script .json file")
    parser.add_argument("output", help="Path to write the output .ymmp file")
    parser.add_argument("--bom", action="store_true", help="Add UTF-8 BOM to the output file")

    args = parser.parse_args()

    with open(args.script, 'r', encoding='utf-8') as f:
        script = json.load(f)

    compiler = YMMPCompiler(args.template)
    compiler.compile(script, args.output, use_bom=args.bom)

if __name__ == "__main__":
    main()
