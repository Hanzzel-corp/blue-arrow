#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

NODE_RE = re.compile(r'^\s*([A-Za-z0-9_]+)\["([^"]+)"\]\s*$')
EDGE_RE = re.compile(r'^\s*([A-Za-z0-9_]+)\s*-->(?:\|([^|]+)\|)?\s*([A-Za-z0-9_]+)\s*$')
SUBGRAPH_RE = re.compile(r'^\s*subgraph\s+([A-Za-z0-9_]+)\["([^"]+)"\]\s*$')
CLASS_RE = re.compile(r'^\s*class\s+(.+?)\s+([A-Za-z0-9_]+)\s*$')
MERMAID_BLOCK_RE = re.compile(r'```mermaid\n(.*?)```', re.DOTALL)


@dataclass
class Edge:
    source_id: str
    source_label: str
    port: str
    target_id: str
    target_label: str
    source_group: str | None = None
    target_group: str | None = None

    def category(self) -> str:
        port = (self.port or '').strip()
        if not port:
            return 'link'
        left = port.split('.')[0].strip()
        if left.endswith(':'):
            left = left[:-1]
        return left


class MermaidFlowParser:
    def __init__(self, text: str):
        self.text = text
        self.nodes: dict[str, str] = {}
        self.groups: dict[str, str] = {}
        self.node_group: dict[str, str] = {}
        self.edges: list[Edge] = []

    def extract_mermaid(self) -> str:
        match = MERMAID_BLOCK_RE.search(self.text)
        if not match:
            raise ValueError('No encontré un bloque ```mermaid ... ``` en el archivo.')
        return match.group(1)

    def parse(self) -> 'MermaidFlowParser':
        mermaid = self.extract_mermaid()
        current_group_id: str | None = None

        for raw_line in mermaid.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('%%') or line == 'flowchart TB' or line == 'direction TB':
                continue

            sub = SUBGRAPH_RE.match(line)
            if sub:
                current_group_id = sub.group(1)
                self.groups[current_group_id] = sub.group(2)
                continue

            if line == 'end':
                current_group_id = None
                continue

            node = NODE_RE.match(line)
            if node:
                node_id, label = node.groups()
                self.nodes[node_id] = label
                if current_group_id:
                    self.node_group[node_id] = current_group_id
                continue

            edge = EDGE_RE.match(line)
            if edge:
                source_id, port, target_id = edge.groups()
                source_label = self.nodes.get(source_id, source_id)
                target_label = self.nodes.get(target_id, target_id)
                self.edges.append(
                    Edge(
                        source_id=source_id,
                        source_label=source_label,
                        port=(port or '').strip(),
                        target_id=target_id,
                        target_label=target_label,
                        source_group=self.groups.get(self.node_group.get(source_id, '')),
                        target_group=self.groups.get(self.node_group.get(target_id, '')),
                    )
                )
                continue

            cls = CLASS_RE.match(line)
            if cls:
                continue

        # segunda pasada para completar labels si hubo aristas antes de definición (por robustez)
        for edge in self.edges:
            edge.source_label = self.nodes.get(edge.source_id, edge.source_id)
            edge.target_label = self.nodes.get(edge.target_id, edge.target_id)
            edge.source_group = self.groups.get(self.node_group.get(edge.source_id, ''), None)
            edge.target_group = self.groups.get(self.node_group.get(edge.target_id, ''), None)

        return self


class FlowGraph:
    def __init__(self, parser: MermaidFlowParser):
        self.nodes = parser.nodes
        self.groups = parser.groups
        self.node_group = parser.node_group
        self.edges = parser.edges
        self.out_edges: dict[str, list[Edge]] = defaultdict(list)
        self.in_edges: dict[str, list[Edge]] = defaultdict(list)
        self.label_to_id: dict[str, str] = {}

        for node_id, label in self.nodes.items():
            self.label_to_id[label.lower()] = node_id
            self.label_to_id[node_id.lower()] = node_id

        for edge in self.edges:
            self.out_edges[edge.source_id].append(edge)
            self.in_edges[edge.target_id].append(edge)

    def resolve(self, name: str) -> str:
        key = name.strip().lower()
        if key in self.label_to_id:
            return self.label_to_id[key]

        exact = [node_id for node_id, label in self.nodes.items() if label.lower() == key]
        if exact:
            return exact[0]

        contains = [node_id for node_id, label in self.nodes.items() if key in label.lower() or key in node_id.lower()]
        if len(contains) == 1:
            return contains[0]
        if len(contains) > 1:
            names = ', '.join(f'{nid} ({self.nodes[nid]})' for nid in contains)
            raise ValueError(f'Ambiguo: "{name}" puede ser {names}')
        raise ValueError(f'No encontré el módulo "{name}"')

    def summary(self) -> dict:
        sources = [n for n in self.nodes if not self.in_edges.get(n)]
        sinks = [n for n in self.nodes if not self.out_edges.get(n)]
        port_counts = Counter(edge.port or 'link' for edge in self.edges)
        category_counts = Counter(edge.category() for edge in self.edges)
        fanout = sorted(((n, len(self.out_edges.get(n, []))) for n in self.nodes), key=lambda x: (-x[1], self.nodes[x[0]].lower()))
        fanin = sorted(((n, len(self.in_edges.get(n, []))) for n in self.nodes), key=lambda x: (-x[1], self.nodes[x[0]].lower()))
        group_counts = Counter(self.groups.get(self.node_group.get(n, ''), 'Sin grupo') for n in self.nodes)
        return {
            'total_nodes': len(self.nodes),
            'total_edges': len(self.edges),
            'sources': [{'id': n, 'label': self.nodes[n]} for n in sources],
            'sinks': [{'id': n, 'label': self.nodes[n]} for n in sinks],
            'top_fanout': [{'id': n, 'label': self.nodes[n], 'count': c} for n, c in fanout[:10]],
            'top_fanin': [{'id': n, 'label': self.nodes[n], 'count': c} for n, c in fanin[:10]],
            'port_counts': dict(port_counts),
            'category_counts': dict(category_counts),
            'group_counts': dict(group_counts),
        }

    def trace_from(self, start: str, depth: int = 5, category: str | None = None) -> list[dict]:
        start_id = self.resolve(start)
        visited: set[tuple[str, str, str]] = set()
        q = deque([(start_id, 0)])
        rows: list[dict] = []

        while q:
            current, level = q.popleft()
            if level >= depth:
                continue
            for edge in self.out_edges.get(current, []):
                if category and edge.category() != category:
                    continue
                key = (edge.source_id, edge.port, edge.target_id)
                if key in visited:
                    continue
                visited.add(key)
                rows.append({
                    'depth': level + 1,
                    'from': edge.source_label,
                    'port': edge.port,
                    'to': edge.target_label,
                    'from_group': edge.source_group,
                    'to_group': edge.target_group,
                })
                q.append((edge.target_id, level + 1))
        return rows

    def trace_to(self, target: str, depth: int = 5, category: str | None = None) -> list[dict]:
        target_id = self.resolve(target)
        visited: set[tuple[str, str, str]] = set()
        q = deque([(target_id, 0)])
        rows: list[dict] = []

        while q:
            current, level = q.popleft()
            if level >= depth:
                continue
            for edge in self.in_edges.get(current, []):
                if category and edge.category() != category:
                    continue
                key = (edge.source_id, edge.port, edge.target_id)
                if key in visited:
                    continue
                visited.add(key)
                rows.append({
                    'depth': level + 1,
                    'from': edge.source_label,
                    'port': edge.port,
                    'to': edge.target_label,
                    'from_group': edge.source_group,
                    'to_group': edge.target_group,
                })
                q.append((edge.source_id, level + 1))
        return rows

    def shortest_path(self, source: str, target: str, category: str | None = None) -> list[dict]:
        source_id = self.resolve(source)
        target_id = self.resolve(target)
        q = deque([source_id])
        parent: dict[str, tuple[str, Edge] | None] = {source_id: None}

        while q:
            current = q.popleft()
            if current == target_id:
                break
            for edge in self.out_edges.get(current, []):
                if category and edge.category() != category:
                    continue
                nxt = edge.target_id
                if nxt not in parent:
                    parent[nxt] = (current, edge)
                    q.append(nxt)

        if target_id not in parent:
            return []

        rev: list[dict] = []
        cur = target_id
        while parent[cur] is not None:
            prev, edge = parent[cur]
            rev.append({
                'from': self.nodes[prev],
                'port': edge.port,
                'to': self.nodes[cur],
                'from_group': self.groups.get(self.node_group.get(prev, ''), None),
                'to_group': self.groups.get(self.node_group.get(cur, ''), None),
            })
            cur = prev
        return list(reversed(rev))

    def module_report(self, name: str) -> dict:
        node_id = self.resolve(name)
        out_list = [asdict(edge) | {'category': edge.category()} for edge in self.out_edges.get(node_id, [])]
        in_list = [asdict(edge) | {'category': edge.category()} for edge in self.in_edges.get(node_id, [])]
        return {
            'id': node_id,
            'label': self.nodes[node_id],
            'group': self.groups.get(self.node_group.get(node_id, ''), None),
            'outgoing_count': len(out_list),
            'incoming_count': len(in_list),
            'outgoing': out_list,
            'incoming': in_list,
        }

    def dataops_paths(self) -> dict[str, list[dict]]:
        scenarios = {
            'telegram_command_to_execution': (
                'interface.telegram',
                'worker.python.desktop',
                None,
            ),
            'telegram_command_to_terminal': (
                'interface.telegram',
                'worker.python.terminal',
                None,
            ),
            'telegram_command_to_browser': (
                'interface.telegram',
                'worker.python.browser',
                None,
            ),
            'router_to_verification': (
                'router.main',
                'verifier.engine.main',
                None,
            ),
            'office_writer_roundtrip': (
                'interface.telegram',
                'office.writer.main',
                None,
            ),
            'execution_feedback_to_user': (
                'verifier.engine.main',
                'interface.telegram',
                None,
            ),
            'execution_feedback_to_memory': (
                'verifier.engine.main',
                'memory.log.main',
                'event',
            ),
        }
        return {
            key: self.shortest_path(src, dst, category=cat)
            for key, (src, dst, cat) in scenarios.items()
        }


def print_table(rows: list[dict]) -> None:
    if not rows:
        print('Sin resultados.')
        return

    columns = list(rows[0].keys())
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            widths[col] = max(widths[col], len(str(row.get(col, ''))))

    header = ' | '.join(col.ljust(widths[col]) for col in columns)
    sep = '-+-'.join('-' * widths[col] for col in columns)
    print(header)
    print(sep)
    for row in rows:
        print(' | '.join(str(row.get(col, '')).ljust(widths[col]) for col in columns))


def load_graph(path: Path) -> FlowGraph:
    text = path.read_text(encoding='utf-8')
    parser = MermaidFlowParser(text).parse()
    return FlowGraph(parser)


def cmd_summary(graph: FlowGraph, as_json: bool) -> None:
    data = graph.summary()
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    print(f'Módulos: {data["total_nodes"]}')
    print(f'Conexiones: {data["total_edges"]}')
    print('\nTop fan-out:')
    print_table(data['top_fanout'])
    print('\nTop fan-in:')
    print_table(data['top_fanin'])
    print('\nCategorías de flujo:')
    print_table([{'category': k, 'count': v} for k, v in sorted(data['category_counts'].items())])


def cmd_trace(graph: FlowGraph, direction: str, module: str, depth: int, category: str | None, as_json: bool) -> None:
    rows = graph.trace_from(module, depth, category) if direction == 'from' else graph.trace_to(module, depth, category)
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        print_table(rows)


def cmd_path(graph: FlowGraph, source: str, target: str, category: str | None, as_json: bool) -> None:
    rows = graph.shortest_path(source, target, category)
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        print_table(rows)


def cmd_module(graph: FlowGraph, module: str, as_json: bool) -> None:
    data = graph.module_report(module)
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    print(f'Módulo: {data["label"]} ({data["id"]})')
    print(f'Capa: {data["group"]}')
    print(f'Entradas: {data["incoming_count"]}')
    print(f'Salidas: {data["outgoing_count"]}')
    print('\nEntradas:')
    print_table([
        {'from': e['source_label'], 'port': e['port'], 'category': e['category']}
        for e in data['incoming']
    ])
    print('\nSalidas:')
    print_table([
        {'to': e['target_label'], 'port': e['port'], 'category': e['category']}
        for e in data['outgoing']
    ])


def cmd_dataops(graph: FlowGraph, as_json: bool) -> None:
    data = graph.dataops_paths()
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    for name, rows in data.items():
        print(f'\n=== {name} ===')
        print_table(rows)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Inspecciona el flujo Mermaid del diagrama de arquitectura de Blueprint v0.'
    )
    parser.add_argument('file', type=Path, help='Ruta al archivo markdown con el bloque Mermaid.')
    parser.add_argument('--json', action='store_true', help='Salida en JSON.')

    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('summary', help='Resumen general del grafo.')

    trace = sub.add_parser('trace', help='Recorre entradas o salidas desde un módulo.')
    trace.add_argument('--direction', choices=['from', 'to'], required=True)
    trace.add_argument('--module', required=True)
    trace.add_argument('--depth', type=int, default=5)
    trace.add_argument('--category', help='Filtrar por categoría: command, event, result, plan, etc.')

    path = sub.add_parser('path', help='Busca el camino más corto entre dos módulos.')
    path.add_argument('--from-module', required=True)
    path.add_argument('--to-module', required=True)
    path.add_argument('--category', help='Filtrar por categoría.')

    module = sub.add_parser('module', help='Detalle de entradas y salidas de un módulo.')
    module.add_argument('--module', required=True)

    sub.add_parser('dataops', help='Escenarios útiles de movimiento de datos.')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    graph = load_graph(args.file)

    if args.command == 'summary':
        cmd_summary(graph, args.json)
    elif args.command == 'trace':
        cmd_trace(graph, args.direction, args.module, args.depth, args.category, args.json)
    elif args.command == 'path':
        cmd_path(graph, args.from_module, args.to_module, args.category, args.json)
    elif args.command == 'module':
        cmd_module(graph, args.module, args.json)
    elif args.command == 'dataops':
        cmd_dataops(graph, args.json)
    else:
        raise AssertionError('Comando no soportado')

    return 0


if __name__ == '__main__':
    sys.exit(main())
