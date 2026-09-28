"""Local administrator CLI for the Intellex knowledge base.

Examples:
    python -m app.kb_admin list
    python -m app.kb_admin remove CONF-001
    python -m app.kb_admin rebuild

Run this only from the trusted Intellex administration environment. Do not
expose document-removal operations as an unauthenticated public API.
"""

import argparse
import json

from .knowledge_base import KnowledgeBase


def main():
    parser = argparse.ArgumentParser(description="Intellex knowledge-base administrator")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List indexed source documents")
    remove = sub.add_parser("remove", help="Remove a document by ID")
    remove.add_argument("doc_id", help="Document ID, e.g. CONF-001")
    remove.add_argument(
        "--keep-source",
        action="store_true",
        help="Remove it from the compiled index but leave the source file on disk",
    )
    sub.add_parser("rebuild", help="Force a full KB rebuild")

    args = parser.parse_args()
    kb = KnowledgeBase()

    if args.command == "list":
        kb.build_index()
        print(json.dumps(kb.list_documents(), indent=2, ensure_ascii=False))
        return

    if args.command == "remove":
        kb.build_index()
        result = kb.remove_document(
            args.doc_id,
            delete_source=not args.keep_source,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "rebuild":
        kb.build_index(force=True)
        print(json.dumps({
            "status": "rebuilt",
            "files": kb.file_names(),
            "chunks": kb.doc_count(),
            "documents": kb.list_documents(),
        }, indent=2, ensure_ascii=False))
        return


if __name__ == "__main__":
    main()
