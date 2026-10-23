"""Lees uitsluitend de structuur van de lokale starter; voer LCP-code nooit uit."""
import argparse
import ast
from pathlib import Path
import re

SAFE_LITERALS = frozenset({
    'LCP_EMAIL', 'LCP_PASSWORD', 'LCP_PUBLISHABLE_KEY',
    'LOCALAPPDATA', '__main__', '__file__',
    'support', 'account.py', 'upstream_worker.py', 'lcp_worker.py',
    'lcp_worker_zigbee_v2.py', 'python.exe', 'pythonw.exe',
    'r', 'rb', 'w', 'wb', 'utf-8', 'utf-8-sig',
})
KNOWN_FILES = (
    '2-START-LCP.cmd', 'LCP-achtergrond.vbs', 'LCP-background.vbs',
    'account.py', 'upstream_worker.py', 'lcp_worker.py',
    'lcp_worker_zigbee_v2.py', 'python.exe', 'pythonw.exe',
)


class HideLiterals(ast.NodeTransformer):
    def visit_Constant(self, node):
        if node.value is None or isinstance(node.value, bool):
            return node
        if isinstance(node.value, str) and node.value in SAFE_LITERALS:
            return node
        return ast.copy_location(ast.Constant(value='<afgeschermd>'), node)


def inspect_launcher(root):
    root = Path(root)
    lines = ['LCP-starterstructuur; geen LCP-code uitgevoerd; vaste waarden afgeschermd.']
    for name in ('2-START-LCP.cmd', 'LCP-achtergrond.vbs', 'LCP-background.vbs'):
        path = root / name
        lines.append('Starter: ' + name)
        if not path.is_file():
            lines.append('  Niet gevonden')
            continue
        try:
            text = path.read_text(encoding='utf-8-sig', errors='replace')
            refs = [file for file in KNOWN_FILES if file.casefold() in text.casefold()]
            lines.append('  Bestandsverwijzingen: ' + ', '.join(refs))
            if name.endswith('.vbs'):
                # Geen onbewerkte VBS-bron: ook daarin kunnen waarden staan.
                for operation in ('Run', 'Exec', 'Sleep', 'CurrentDirectory', 'Environment'):
                    lines.append(f'  Gebruikt {operation}: ' + str(bool(re.search(r'(?i)\b' + operation + r'\b', text))))
        except OSError:
            lines.append('  Niet leesbaar')
    path = root / 'support' / 'account.py'
    lines.append('Python-starter: support/account.py')
    try:
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        # Alleen de starter, nooit de worker of een inlogbestand uitlezen.
        cleaned = ast.fix_missing_locations(HideLiterals().visit(tree))
        source = ast.unparse(cleaned).splitlines()
        lines.extend(source[:350])
        if len(source) > 350:
            lines.append('[structuur ingekort na 350 regels]')
    except (OSError, SyntaxError, ValueError, RecursionError):
        # Exceptions kunnen bronregels met geheimen bevatten; geen details tonen.
        lines.append('Starterstructuur kon niet worden gelezen.')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    print(inspect_launcher(args.root))


if __name__ == '__main__':
    main()
