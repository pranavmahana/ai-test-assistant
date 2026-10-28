"""Command-line interface for AI Test Assistant."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ai_test_assistant.evaluation.evaluator import TestEvaluator
from ai_test_assistant.generator.claude_client import ClaudeTestGenerator
from ai_test_assistant.generator.mock_generator import MockClaudeGenerator
from ai_test_assistant.parser.chunker import EndpointChunker
from ai_test_assistant.parser.spec_parser import SpecParser
from ai_test_assistant.pipeline import Pipeline
from ai_test_assistant.redteam.redteam_harness import RedTeamHarness
from ai_test_assistant.retrieval.tfidf_retriever import TfidfRetriever
from ai_test_assistant.security.safety_scanner import SafetyScanner

console = Console(highlight=False)


def handle_chunk(args: argparse.Namespace) -> None:
    """Handle 'chunk' command: parse and display endpoint chunks."""
    spec_path = Path(args.spec)
    if not spec_path.exists():
        console.print(f"[red]Error:[/red] Spec file not found: {spec_path}")
        sys.exit(1)

    parser = SpecParser.from_file(spec_path)
    chunker = EndpointChunker(parser)
    chunks = chunker.chunk_all()

    table = Table(title=f"Endpoint Chunks ({len(chunks)} total) - {parser.title}")
    table.add_column("Method", style="cyan", width=8)
    table.add_column("Path", style="green")
    table.add_column("Operation ID", style="yellow")
    table.add_column("Params", justify="right")
    table.add_column("Security", style="magenta")

    for chunk in chunks:
        sec_str = ", ".join(chunk.security) if chunk.security else "None"
        table.add_row(
            chunk.method.value,
            chunk.path,
            chunk.operation_id or "-",
            str(len(chunk.parameters)),
            sec_str,
        )

    console.print(table)


def handle_retrieve(args: argparse.Namespace) -> None:
    """Handle 'retrieve' command: search endpoints using TF-IDF."""
    spec_path = Path(args.spec)
    if not spec_path.exists():
        console.print(f"[red]Error:[/red] Spec file not found: {spec_path}")
        sys.exit(1)

    parser = SpecParser.from_file(spec_path)
    chunker = EndpointChunker(parser)
    chunks = chunker.chunk_all()

    retriever = TfidfRetriever(chunks)
    results = retriever.retrieve(query=args.query, top_k=args.top_k)

    table = Table(title=f"TF-IDF Retrieval Results for: '{args.query}'")
    table.add_column("Rank", justify="center", width=6)
    table.add_column("Score", justify="right", style="cyan", width=8)
    table.add_column("Endpoint", style="green")
    table.add_column("Summary", style="white")

    for res in results:
        table.add_row(
            str(res.rank),
            f"{res.score:.4f}",
            res.endpoint_key,
            res.chunk.summary or "-",
        )

    console.print(table)


def handle_generate(args: argparse.Namespace) -> None:
    """Handle 'generate' command: generate pytest API tests."""
    spec_path = Path(args.spec)
    if not spec_path.exists():
        console.print(f"[red]Error:[/red] Spec file not found: {spec_path}")
        sys.exit(1)

    parser = SpecParser.from_file(spec_path)
    chunker = EndpointChunker(parser)
    chunks = chunker.chunk_all()

    if args.query:
        retriever = TfidfRetriever(chunks)
        results = retriever.retrieve(query=args.query, top_k=args.top_k)
        target_chunks = [r.chunk for r in results]
    else:
        target_chunks = chunks[:args.top_k]

    if not target_chunks:
        console.print("[yellow]No matching endpoint chunks found to generate tests for.[/yellow]")
        return

    console.print(f"[cyan]Selected {len(target_chunks)} endpoint chunks for generation.[/cyan]")

    if args.mock:
        generator = MockClaudeGenerator()
    else:
        try:
            generator = ClaudeTestGenerator(api_key=args.api_key)
        except Exception as e:
            console.print(f"[yellow]Claude API not available ({e}). Falling back to mock generator.[/yellow]")
            generator = MockClaudeGenerator()

    test_code = generator.generate(
        chunks=target_chunks,
        query=args.query,
        base_url=args.base_url or parser.base_url,
    )

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(test_code, encoding="utf-8")
        console.print(f"[green][OK] Generated tests saved to:[/green] {out_path}")
    else:
        console.print(Panel(test_code, title="Generated Pytest Suite", border_style="green"))


def handle_evaluate(args: argparse.Namespace) -> None:
    """Handle 'evaluate' command: score a test file against a spec."""
    spec_path = Path(args.spec)
    test_path = Path(args.test_file)

    if not spec_path.exists():
        console.print(f"[red]Error:[/red] Spec file not found: {spec_path}")
        sys.exit(1)
    if not test_path.exists():
        console.print(f"[red]Error:[/red] Test file not found: {test_path}")
        sys.exit(1)

    parser = SpecParser.from_file(spec_path)
    chunker = EndpointChunker(parser)
    chunks = chunker.chunk_all()

    code = test_path.read_text(encoding="utf-8")
    evaluator = TestEvaluator()
    report = evaluator.evaluate(code=code, target_chunks=chunks)

    # Display evaluation card
    table = Table(title=f"Evaluation Scorecard - Grade: {report.grade} ({report.composite_score:.1f}/100)")
    table.add_column("Metric Dimension", style="cyan")
    table.add_column("Details", style="white")
    table.add_column("Score", justify="right", style="green")

    table.add_row(
        "1. Syntax Validity",
        "Valid Python syntax" if report.syntax.is_valid else f"Syntax Error: {report.syntax.error_message}",
        f"{report.syntax.score:.1f} / 20.0",
    )
    table.add_row(
        "2. Assertion Quality",
        f"{report.assertions.total_assertions} assertions ({report.assertions.assertions_per_test:.1f}/test), {report.assertions.status_code_checks} status checks",
        f"{report.assertions.score:.1f} / 20.0",
    )
    table.add_row(
        "3. Anti-Hallucination",
        f"{report.hallucinations.hallucination_count} invented endpoints",
        f"{report.hallucinations.score:.1f} / 25.0",
    )
    table.add_row(
        "4. Endpoint Coverage",
        f"{report.coverage.covered_count}/{report.coverage.target_count} endpoints covered ({report.coverage.coverage_percentage:.1f}%)",
        f"{report.coverage.score:.1f} / 20.0",
    )
    table.add_row(
        "5. Negative Tests",
        f"{report.negative_tests.negative_tests}/{report.negative_tests.total_tests} tests are negative ({report.negative_tests.negative_test_ratio * 100:.1f}%)",
        f"{report.negative_tests.score:.1f} / 15.0",
    )

    console.print(table)

    if report.passed:
        console.print("[bold green][PASS] VERDICT: PASSED[/bold green]")
    else:
        console.print("[bold red][FAIL] VERDICT: FAILED[/bold red]")

    if report.recommendations:
        console.print("\n[yellow]Recommendations for Improvement:[/yellow]")
        for rec in report.recommendations:
            console.print(f"  • {rec}")

    if args.json:
        json_path = Path(args.json)
        json_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        console.print(f"[green]Report exported to {json_path}[/green]")


def handle_scan(args: argparse.Namespace) -> None:
    """Handle 'scan' command: run AST safety scanner on a Python file."""
    path = Path(args.target)
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {path}")
        sys.exit(1)

    code = path.read_text(encoding="utf-8")
    report = SafetyScanner.scan(code)

    if report.is_safe:
        console.print(f"[bold green][PASS] AST Safety Scan PASSED for {path}[/bold green]")
        if report.warnings:
            console.print("[yellow]Warnings:[/yellow]")
            for w in report.warnings:
                console.print(f"  • {w}")
    else:
        console.print(f"[bold red][FAIL] AST Safety Scan FAILED for {path}[/bold red]")
        console.print(f"Detected {len(report.violations)} security violation(s):")
        for v in report.violations:
            console.print(f"  [red]• [{v.severity.value}] {v.rule} (Line {v.line_number}): {v.message}[/red]")
        sys.exit(1)


def handle_redteam(args: argparse.Namespace) -> None:
    """Handle 'redteam' command: run adversarial prompt-injection test benchmark."""
    harness = RedTeamHarness()
    report = harness.run_benchmark(base_spec_path=args.spec)

    table = Table(title=f"Prompt-Injection Red-Team Benchmark - Resilience: {report.resistance_percentage:.1f}%")
    table.add_column("Scenario", style="cyan")
    table.add_column("Payload Preview", style="white", max_width=40)
    table.add_column("Result", justify="center")
    table.add_column("Details", style="magenta")

    for r in report.results:
        res_str = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        table.add_row(
            r.attack_name,
            r.injected_payload[:37] + "...",
            res_str,
            r.details,
        )

    console.print(table)
    if report.passed:
        console.print("[bold green][PASS] ALL ADVERSARIAL ATTACKS SUCCESSFULLY DEFENDED[/bold green]")
    else:
        console.print("[bold red][FAIL] ADVERSARIAL VULNERABILITIES DETECTED[/bold red]")
        sys.exit(1)


def handle_pipeline(args: argparse.Namespace) -> None:
    """Handle 'pipeline' command: execute end-to-end workflow."""
    spec_path = Path(args.spec)
    if not spec_path.exists():
        console.print(f"[red]Error:[/red] Spec file not found: {spec_path}")
        sys.exit(1)

    pipeline = Pipeline(spec_source=spec_path, use_mock=args.mock, api_key=args.api_key)
    result = pipeline.run(query=args.query, top_k=args.top_k, base_url=args.base_url)

    # Save generated tests
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result.generated_code, encoding="utf-8")
        console.print(f"[green][OK] Generated tests saved to:[/green] {out_path}")

    # Display evaluation score
    eval_rep = result.evaluation_report
    console.print(
        f"\n[bold]Evaluation Verdict:[/bold] {'[green]PASS[/green]' if eval_rep.passed else '[red]FAIL[/red]'} "
        f"(Grade: {eval_rep.grade}, Score: {eval_rep.composite_score:.1f}/100)"
    )
    console.print(
        f"[bold]Safety Scan Verdict:[/bold] {'[green]SAFE[/green]' if result.safety_report.is_safe else '[red]UNSAFE[/red]'}"
    )


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="ai-test-assistant",
        description="AI Test Assistant - LLM-Powered API Test Generation & Evaluation Pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # chunk
    chunk_p = subparsers.add_parser("chunk", help="Chunk an OpenAPI specification into retrievable endpoints.")
    chunk_p.add_argument("--spec", required=True, help="Path to OpenAPI JSON/YAML spec.")

    # retrieve
    ret_p = subparsers.add_parser("retrieve", help="Search spec endpoints using TF-IDF retrieval.")
    ret_p.add_argument("--spec", required=True, help="Path to OpenAPI spec.")
    ret_p.add_argument("--query", required=True, help="Natural language query.")
    ret_p.add_argument("--top-k", type=int, default=5, help="Number of endpoints to retrieve.")

    # generate
    gen_p = subparsers.add_parser("generate", help="Generate pytest API tests from spec.")
    gen_p.add_argument("--spec", required=True, help="Path to OpenAPI spec.")
    gen_p.add_argument("--query", help="Focus query for endpoint retrieval.")
    gen_p.add_argument("--top-k", type=int, default=5, help="Max endpoints to include.")
    gen_p.add_argument("--output", "-o", help="File to write generated tests to.")
    gen_p.add_argument("--base-url", help="Base URL for target API.")
    gen_p.add_argument("--api-key", help="Anthropic API key.")
    gen_p.add_argument("--mock", action="store_true", help="Force offline mock generation.")

    # evaluate
    eval_p = subparsers.add_parser("evaluate", help="Score generated tests against OpenAPI spec.")
    eval_p.add_argument("--spec", required=True, help="Path to OpenAPI spec.")
    eval_p.add_argument("--test-file", required=True, help="Path to Python test file.")
    eval_p.add_argument("--json", help="Path to export JSON report.")

    # scan
    scan_p = subparsers.add_parser("scan", help="Run AST safety scanner on a Python test file.")
    scan_p.add_argument("--target", required=True, help="Python file to inspect.")

    # redteam
    rt_p = subparsers.add_parser("redteam", help="Run adversarial prompt-injection benchmark.")
    rt_p.add_argument("--spec", help="Optional custom adversarial spec.")

    # pipeline
    pipe_p = subparsers.add_parser("pipeline", help="Run end-to-end generate & evaluate pipeline.")
    pipe_p.add_argument("--spec", required=True, help="Path to OpenAPI spec.")
    pipe_p.add_argument("--query", help="Query to focus test generation.")
    pipe_p.add_argument("--top-k", type=int, default=5, help="Max endpoints.")
    pipe_p.add_argument("--output", "-o", help="Output test file path.")
    pipe_p.add_argument("--base-url", help="Base URL.")
    pipe_p.add_argument("--mock", action="store_true", help="Use offline mock generator.")
    pipe_p.add_argument("--api-key", help="Anthropic API key.")

    args = parser.parse_args()

    if args.command == "chunk":
        handle_chunk(args)
    elif args.command == "retrieve":
        handle_retrieve(args)
    elif args.command == "generate":
        handle_generate(args)
    elif args.command == "evaluate":
        handle_evaluate(args)
    elif args.command == "scan":
        handle_scan(args)
    elif args.command == "redteam":
        handle_redteam(args)
    elif args.command == "pipeline":
        handle_pipeline(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
