import argparse

from evals.generator.build import write
from evals.generator.render import RENDER


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="document ids (default: all)")
    args = parser.parse_args()
    for doc_id in args.ids or RENDER:
        if doc_id not in RENDER:
            parser.error(f"unknown document id {doc_id}")
        print(write(doc_id).name)


if __name__ == "__main__":
    main()
