"""Document chunking strategies for RAG indexing.

Provides heading-aware and content-aware chunking:
- MarkdownChunker: Splits on heading boundaries
- OpenAPIChunker: One chunk per endpoint

CRITICAL: Uses tiktoken for accurate token counting.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import tiktoken

from app.core.config import get_settings


@dataclass
class ChunkData:
    """Represents a single chunk of document content.

    Args:
        content: The text content of the chunk.
        index: Position of this chunk in the source document.
        token_count: Number of tokens in the content.
        metadata: Additional context (heading, section_path, etc.).
    """

    content: str
    index: int
    token_count: int
    metadata: dict[str, Any] = field(default_factory=lambda: {})


class BaseChunker(ABC):
    """Abstract base class for document chunkers.

    All chunkers must:
    - Use tiktoken for token counting (cl100k_base encoding)
    - Respect chunk_size and chunk_overlap settings
    - Never exceed 8191 tokens per chunk (OpenAI limit)
    """

    MAX_TOKENS_PER_CHUNK = 8191  # OpenAI embedding input limit

    def __init__(self) -> None:
        """Initialize chunker with settings and tokenizer."""
        self.settings = get_settings()
        self.chunk_size = self.settings.rag_chunk_size
        self.chunk_overlap = self.settings.rag_chunk_overlap
        self.min_chunk_size = self.settings.rag_min_chunk_size
        self._encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken.

        Args:
            text: Text to count tokens for.

        Returns:
            Number of tokens.
        """
        return len(self._encoder.encode(text))

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to a maximum number of tokens.

        Args:
            text: Text to truncate.
            max_tokens: Maximum number of tokens.

        Returns:
            Truncated text.
        """
        tokens = self._encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self._encoder.decode(tokens[:max_tokens])

    @abstractmethod
    def chunk(self, content: str) -> list[ChunkData]:
        """Split content into chunks.

        Args:
            content: Full document content.

        Returns:
            List of ChunkData objects.
        """
        pass


class MarkdownChunker(BaseChunker):
    """Chunks markdown documents by heading boundaries.

    Splits content at heading boundaries (# ## ### etc.) while:
    - Respecting chunk_size limits
    - Including heading hierarchy in metadata
    - Preserving context through overlap
    """

    # Regex to match markdown headings
    HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    def chunk(self, content: str) -> list[ChunkData]:
        """Split markdown content into heading-aware chunks.

        Args:
            content: Markdown document content.

        Returns:
            List of ChunkData with heading metadata.
        """
        chunks: list[ChunkData] = []
        sections = self._split_by_headings(content)

        current_chunk = ""
        current_heading_path: list[str] = []
        chunk_index = 0

        for section in sections:
            section_content = section["content"]
            heading = section.get("heading")
            level = section.get("level", 0)

            # Update heading path based on level
            if heading:
                current_heading_path = self._update_heading_path(
                    current_heading_path, heading, level
                )

            section_tokens = self.count_tokens(section_content)

            # If section alone exceeds chunk size, split it further
            if section_tokens > self.chunk_size:
                # Flush current chunk if any
                if current_chunk.strip():
                    chunks.append(
                        self._create_chunk(
                            current_chunk.strip(), chunk_index, current_heading_path.copy()
                        )
                    )
                    chunk_index += 1
                    current_chunk = ""

                # Split large section into smaller chunks
                sub_chunks = self._split_large_section(section_content, current_heading_path.copy())
                for sub_chunk in sub_chunks:
                    sub_chunk.index = chunk_index
                    chunks.append(sub_chunk)
                    chunk_index += 1
                continue

            # Check if adding this section exceeds chunk size
            combined = current_chunk + section_content
            combined_tokens = self.count_tokens(combined)

            if combined_tokens > self.chunk_size:
                # Save current chunk and start new one
                if current_chunk.strip():
                    chunks.append(
                        self._create_chunk(
                            current_chunk.strip(), chunk_index, current_heading_path.copy()
                        )
                    )
                    chunk_index += 1

                # Add overlap from previous chunk
                overlap_text = self._get_overlap_text(current_chunk)
                current_chunk = overlap_text + section_content
            else:
                current_chunk = combined

        # Don't forget the last chunk
        # Include it even if small when it's the only content
        if current_chunk.strip():
            token_count = self.count_tokens(current_chunk.strip())
            # Include small chunks if: we have no other chunks OR it meets min size
            if len(chunks) == 0 or token_count >= self.min_chunk_size:
                chunks.append(
                    self._create_chunk(
                        current_chunk.strip(), chunk_index, current_heading_path.copy()
                    )
                )

        return chunks

    def _split_by_headings(self, content: str) -> list[dict[str, Any]]:
        """Split content at heading boundaries.

        Args:
            content: Markdown content.

        Returns:
            List of sections with heading info.
        """
        sections: list[dict[str, Any]] = []
        lines = content.split("\n")
        current_section: dict[str, Any] = {"content": "", "heading": None, "level": 0}

        for line in lines:
            match = self.HEADING_PATTERN.match(line)
            if match:
                # Save current section if it has content
                if current_section["content"].strip():
                    sections.append(current_section)

                # Start new section with this heading
                level = len(match.group(1))
                heading = match.group(2).strip()
                current_section = {
                    "content": line + "\n",
                    "heading": heading,
                    "level": level,
                }
            else:
                current_section["content"] += line + "\n"

        # Add final section
        if current_section["content"].strip():
            sections.append(current_section)

        return sections

    def _update_heading_path(self, current_path: list[str], heading: str, level: int) -> list[str]:
        """Update the heading path based on the new heading level.

        Args:
            current_path: Current list of headings.
            heading: New heading text.
            level: Heading level (1-6).

        Returns:
            Updated heading path.
        """
        # Truncate path to current level and add new heading
        new_path = current_path[: level - 1]
        new_path.append(heading)
        return new_path

    def _split_large_section(self, content: str, heading_path: list[str]) -> list[ChunkData]:
        """Split a large section into smaller chunks by sentences/paragraphs.

        Args:
            content: Section content that exceeds chunk size.
            heading_path: Current heading hierarchy.

        Returns:
            List of smaller chunks.
        """
        chunks: list[ChunkData] = []
        paragraphs = content.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_tokens = self.count_tokens(para)

            # If single paragraph exceeds limit, split by sentences
            if para_tokens > self.chunk_size:
                if current_chunk.strip():
                    chunks.append(self._create_chunk(current_chunk.strip(), 0, heading_path))
                    current_chunk = ""

                sentence_chunks = self._split_by_sentences(para, heading_path)
                chunks.extend(sentence_chunks)
                continue

            combined = current_chunk + "\n\n" + para if current_chunk else para
            combined_tokens = self.count_tokens(combined)

            if combined_tokens > self.chunk_size:
                if current_chunk.strip():
                    chunks.append(self._create_chunk(current_chunk.strip(), 0, heading_path))
                current_chunk = para
            else:
                current_chunk = combined

        if current_chunk.strip():
            chunks.append(self._create_chunk(current_chunk.strip(), 0, heading_path))

        return chunks

    def _split_by_sentences(self, text: str, heading_path: list[str]) -> list[ChunkData]:
        """Split text by sentences when paragraphs are too large.

        Args:
            text: Text to split.
            heading_path: Current heading hierarchy.

        Returns:
            List of sentence-based chunks.
        """
        chunks: list[ChunkData] = []
        # Simple sentence splitting (handles . ? !)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        current_chunk = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_tokens = self.count_tokens(sentence)

            # If single sentence exceeds limit, truncate it
            if sentence_tokens > self.MAX_TOKENS_PER_CHUNK:
                if current_chunk.strip():
                    chunks.append(self._create_chunk(current_chunk.strip(), 0, heading_path))
                    current_chunk = ""

                truncated = self._truncate_to_tokens(sentence, self.MAX_TOKENS_PER_CHUNK)
                chunks.append(self._create_chunk(truncated, 0, heading_path))
                continue

            combined = current_chunk + " " + sentence if current_chunk else sentence
            combined_tokens = self.count_tokens(combined)

            if combined_tokens > self.chunk_size:
                if current_chunk.strip():
                    chunks.append(self._create_chunk(current_chunk.strip(), 0, heading_path))
                current_chunk = sentence
            else:
                current_chunk = combined

        if current_chunk.strip():
            chunks.append(self._create_chunk(current_chunk.strip(), 0, heading_path))

        return chunks

    def _get_overlap_text(self, text: str) -> str:
        """Get the last N tokens of text for overlap.

        Args:
            text: Text to get overlap from.

        Returns:
            Overlap text.
        """
        if not text or self.chunk_overlap <= 0:
            return ""

        tokens = self._encoder.encode(text)
        if len(tokens) <= self.chunk_overlap:
            return text

        overlap_tokens = tokens[-self.chunk_overlap :]
        return self._encoder.decode(overlap_tokens)

    def _create_chunk(self, content: str, index: int, heading_path: list[str]) -> ChunkData:
        """Create a ChunkData object with metadata.

        Args:
            content: Chunk content.
            index: Chunk index.
            heading_path: Heading hierarchy.

        Returns:
            ChunkData instance.
        """
        token_count = self.count_tokens(content)
        metadata: dict[str, Any] = {}

        if heading_path:
            metadata["heading"] = heading_path[-1]
            metadata["section_path"] = heading_path

        return ChunkData(
            content=content,
            index=index,
            token_count=token_count,
            metadata=metadata,
        )


class OpenAPIChunker(BaseChunker):
    """Chunks OpenAPI specifications by endpoint.

    Creates one chunk per endpoint containing:
    - Path and method
    - Operation summary and description
    - Parameters and request body schema
    - Response schemas
    """

    def chunk(self, content: str) -> list[ChunkData]:
        """Split OpenAPI spec into endpoint-based chunks.

        Args:
            content: OpenAPI JSON/YAML content.

        Returns:
            List of ChunkData, one per endpoint.
        """
        chunks: list[ChunkData] = []

        spec_data: dict[str, Any]
        try:
            spec_data = json.loads(content)
        except json.JSONDecodeError:
            # Try YAML if JSON fails
            try:
                import yaml  # type: ignore[import-untyped]

                parsed = yaml.safe_load(content)
                # yaml.safe_load can return non-dict for simple strings
                if not isinstance(parsed, dict):
                    return MarkdownChunker().chunk(content)
                spec_data = parsed  # pyright: ignore[reportUnknownVariableType]
            except Exception:
                # Fall back to treating as markdown
                return MarkdownChunker().chunk(content)

        paths: dict[str, Any] = spec_data.get("paths", {})
        chunk_index = 0

        # Also include info section as first chunk
        info: dict[str, Any] = spec_data.get("info", {})
        if info:
            servers: list[dict[str, Any]] = spec_data.get("servers", [])
            info_chunk = self._create_info_chunk(info, servers)
            info_chunk.index = chunk_index
            chunks.append(info_chunk)
            chunk_index += 1

        # Create chunk for each endpoint
        for path_key, methods in paths.items():
            path: str = str(path_key)
            if not isinstance(methods, dict):
                continue

            methods_dict: dict[str, Any] = dict(methods)  # pyright: ignore[reportUnknownArgumentType]
            for method_name, operation in methods_dict.items():
                if method_name.startswith("x-") or not isinstance(operation, dict):
                    continue

                operation_dict: dict[str, Any] = dict(operation)  # pyright: ignore[reportUnknownArgumentType]
                chunk = self._create_endpoint_chunk(path, method_name, operation_dict, spec_data)
                chunk.index = chunk_index
                chunks.append(chunk)
                chunk_index += 1

        return chunks

    def _create_info_chunk(self, info: dict[str, Any], servers: list[dict[str, Any]]) -> ChunkData:
        """Create a chunk for API info section.

        Args:
            info: OpenAPI info object.
            servers: OpenAPI servers array.

        Returns:
            ChunkData for API overview.
        """
        parts: list[str] = []
        title = info.get("title", "API")
        version = info.get("version", "")

        parts.append(f"# {title}")
        if version:
            parts.append(f"Version: {version}")
        if info.get("description"):
            parts.append(f"\n{info['description']}")
        if servers:
            parts.append("\n## Servers")
            for server in servers:
                url = server.get("url", "")
                desc = server.get("description", "")
                parts.append(f"- {url}" + (f" ({desc})" if desc else ""))

        content = "\n".join(parts)
        return ChunkData(
            content=content,
            index=0,
            token_count=self.count_tokens(content),
            metadata={"type": "api_info", "title": title},
        )

    def _create_endpoint_chunk(
        self,
        path: str,
        method: str,
        operation: dict[str, Any],
        spec: dict[str, Any],
    ) -> ChunkData:
        """Create a chunk for a single API endpoint.

        Args:
            path: Endpoint path.
            method: HTTP method.
            operation: OpenAPI operation object.
            spec: Full OpenAPI spec (for dereferencing).

        Returns:
            ChunkData for the endpoint.
        """
        parts: list[str] = []

        # Endpoint header
        operation_id = operation.get("operationId", f"{method}_{path}")
        summary = operation.get("summary", "")
        parts.append(f"## {method.upper()} {path}")
        if summary:
            parts.append(f"**{summary}**")

        # Description
        if operation.get("description"):
            parts.append(f"\n{operation['description']}")

        # Tags
        tags = operation.get("tags", [])
        if tags:
            parts.append(f"\nTags: {', '.join(tags)}")

        # Parameters
        params = operation.get("parameters", [])
        if params:
            parts.append("\n### Parameters")
            for param in params:
                name = param.get("name", "")
                location = param.get("in", "")
                required = param.get("required", False)
                desc = param.get("description", "")
                req_str = " (required)" if required else ""
                parts.append(f"- `{name}` ({location}){req_str}: {desc}")

        # Request body
        request_body = operation.get("requestBody", {})
        if request_body:
            parts.append("\n### Request Body")
            content_types = request_body.get("content", {})
            for ct, schema_info in content_types.items():
                parts.append(f"Content-Type: {ct}")
                if "schema" in schema_info:
                    schema_str = self._format_schema(schema_info["schema"], spec)
                    parts.append(f"```json\n{schema_str}\n```")

        # Responses
        responses = operation.get("responses", {})
        if responses:
            parts.append("\n### Responses")
            for status, response in responses.items():
                desc = response.get("description", "")
                parts.append(f"- **{status}**: {desc}")

        content = "\n".join(parts)

        # Ensure we don't exceed token limit
        token_count = self.count_tokens(content)
        if token_count > self.MAX_TOKENS_PER_CHUNK:
            content = self._truncate_to_tokens(content, self.MAX_TOKENS_PER_CHUNK)
            token_count = self.count_tokens(content)

        return ChunkData(
            content=content,
            index=0,
            token_count=token_count,
            metadata={
                "type": "endpoint",
                "path": path,
                "method": method.upper(),
                "operation_id": operation_id,
                "tags": tags,
            },
        )

    def _format_schema(self, schema: dict[str, Any], spec: dict[str, Any], depth: int = 0) -> str:
        """Format a JSON schema for display.

        Args:
            schema: JSON schema object.
            spec: Full OpenAPI spec (for $ref resolution).
            depth: Current recursion depth.

        Returns:
            Formatted schema string.
        """
        if depth > 3:  # Prevent deep recursion
            return "{...}"

        # Handle $ref
        if "$ref" in schema:
            ref = schema["$ref"]
            resolved = self._resolve_ref(ref, spec)
            if resolved:
                return self._format_schema(resolved, spec, depth + 1)
            return f'{{"$ref": "{ref}"}}'

        # Simple formatting
        try:
            return json.dumps(schema, indent=2)[:500]  # Limit size
        except (TypeError, ValueError):
            return str(schema)[:500]

    def _resolve_ref(self, ref: str, spec: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve a $ref pointer in the OpenAPI spec.

        Args:
            ref: Reference string (e.g., "#/components/schemas/User").
            spec: Full OpenAPI spec.

        Returns:
            Resolved schema or None.
        """
        if not ref.startswith("#/"):
            return None

        parts = ref[2:].split("/")
        current: Any = spec

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]  # pyright: ignore[reportUnknownVariableType]
            else:
                return None

        if isinstance(current, dict):
            return dict(current)  # pyright: ignore[reportUnknownArgumentType]
        return None


def get_chunker(source_type: str) -> BaseChunker:
    """Factory function to get the appropriate chunker.

    Args:
        source_type: Type of source (markdown, openapi).

    Returns:
        Appropriate chunker instance.

    Raises:
        ValueError: If source_type is not supported.
    """
    chunkers = {
        "markdown": MarkdownChunker,
        "openapi": OpenAPIChunker,
    }

    if source_type not in chunkers:
        raise ValueError(f"Unsupported source type: {source_type}")

    return chunkers[source_type]()
