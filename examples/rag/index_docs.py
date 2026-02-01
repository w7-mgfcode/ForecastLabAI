#!/usr/bin/env python
"""Example: Index documentation into RAG knowledge base.

This script demonstrates how to index markdown documentation
from the docs/ directory into the RAG knowledge base.

Usage:
    # Make sure the API is running
    uv run uvicorn app.main:app --reload --port 8123

    # Run this script
    uv run python examples/rag/index_docs.py

Requirements:
    - OPENAI_API_KEY environment variable must be set
    - PostgreSQL with pgvector must be running (docker-compose up -d)
    - Migrations applied (uv run alembic upgrade head)
"""

import asyncio
from pathlib import Path

import httpx


async def index_markdown_docs(base_url: str = "http://localhost:8123") -> None:
    """Index all markdown docs from docs/ directory.

    Args:
        base_url: Base URL of the API server.
    """
    docs_dir = Path("docs")

    if not docs_dir.exists():
        print(f"Error: {docs_dir} directory not found")
        return

    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        # Find all markdown files
        md_files = list(docs_dir.rglob("*.md"))
        print(f"Found {len(md_files)} markdown files to index")

        total_chunks = 0
        total_tokens = 0
        indexed = 0
        unchanged = 0
        failed = 0

        for md_file in md_files:
            try:
                # Read file content
                content = md_file.read_text(encoding="utf-8")

                # Index the document
                response = await client.post(
                    "/rag/index",
                    json={
                        "source_type": "markdown",
                        "source_path": str(md_file),
                        "content": content,
                        "metadata": {
                            "category": "documentation",
                            "file_type": "markdown",
                        },
                    },
                )

                if response.status_code in (200, 201):
                    result = response.json()
                    status = result["status"]

                    if status == "unchanged":
                        unchanged += 1
                        print(f"  [unchanged] {md_file}")
                    else:
                        indexed += 1
                        total_chunks += result["chunks_created"]
                        total_tokens += result["tokens_processed"]
                        print(
                            f"  [{status}] {md_file}: "
                            f"{result['chunks_created']} chunks, "
                            f"{result['tokens_processed']} tokens"
                        )
                else:
                    failed += 1
                    print(f"  [FAILED] {md_file}: {response.status_code} - {response.text}")

            except Exception as e:
                failed += 1
                print(f"  [ERROR] {md_file}: {e}")

        print("\n" + "=" * 50)
        print("Indexing Summary:")
        print(f"  Indexed: {indexed}")
        print(f"  Unchanged: {unchanged}")
        print(f"  Failed: {failed}")
        print(f"  Total chunks created: {total_chunks}")
        print(f"  Total tokens processed: {total_tokens}")


async def index_readme(base_url: str = "http://localhost:8123") -> None:
    """Index the main README.md file.

    Args:
        base_url: Base URL of the API server.
    """
    readme_path = Path("README.md")

    if not readme_path.exists():
        print("README.md not found")
        return

    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        content = readme_path.read_text(encoding="utf-8")

        response = await client.post(
            "/rag/index",
            json={
                "source_type": "markdown",
                "source_path": str(readme_path),
                "content": content,
                "metadata": {"category": "overview"},
            },
        )

        if response.status_code == 201:
            result = response.json()
            print(f"README.md indexed: {result['chunks_created']} chunks ({result['status']})")
        else:
            print(f"Failed to index README.md: {response.status_code}")


async def list_sources(base_url: str = "http://localhost:8123") -> None:
    """List all indexed sources.

    Args:
        base_url: Base URL of the API server.
    """
    async with httpx.AsyncClient(base_url=base_url) as client:
        response = await client.get("/rag/sources")

        if response.status_code == 200:
            data = response.json()
            print(f"\nIndexed Sources: {data['total_sources']}")
            print(f"Total Chunks: {data['total_chunks']}")
            print("\nSources:")
            for source in data["sources"]:
                print(f"  - {source['source_path']} ({source['chunk_count']} chunks)")
        else:
            print(f"Failed to list sources: {response.status_code}")


async def main() -> None:
    """Main entry point."""
    print("RAG Knowledge Base - Document Indexer")
    print("=" * 50)

    # Index README first
    print("\n1. Indexing README.md...")
    await index_readme()

    # Index documentation
    print("\n2. Indexing docs/ directory...")
    await index_markdown_docs()

    # List all sources
    print("\n3. Listing indexed sources...")
    await list_sources()


if __name__ == "__main__":
    asyncio.run(main())
